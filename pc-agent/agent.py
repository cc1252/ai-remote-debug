#!/usr/bin/env python3
"""PC Host Agent for Android Remote Debug Relay.

装在客户电脑上,通过 Relay 上线成为一个 "host" 设备。
你可以远程下发命令,由这台电脑执行 adb / fastboot 等,
即使客户手机系统死机或进入 fastboot 也能通过电脑救砖。

协议复用 mobile-executor 的 /ws/mobile/{device_id} 通道:
  - 收到 {type:command, requestId, action, args} 后执行并回 {type:result,...}
  - host.exec      : 在本机执行任意命令 (shell=True)
  - host.adb       : 等价于 host.exec, 但命令前缀固定为 adb 可执行文件
  - host.fastboot  : 同上, 前缀 fastboot
  - host.which     : 返回 adb/fastboot 路径与版本, 用于自检

配置优先级: 命令行参数 > 环境变量 > agent.config.json > 内置默认。
"""
import argparse
import asyncio
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:
    print("缺少 websockets 库, 请先: pip install websockets", file=sys.stderr)
    raise SystemExit(1)

# ---- 内置默认 (可被打包时改写 / 配置文件覆盖) ----
DEFAULT_RELAY_WS = "ws://127.0.0.1:8000/ws/mobile"
DEFAULT_TOKEN = ""

HEARTBEAT_SECONDS = 15
RECONNECT_DELAY_SECONDS = 5
MAX_STDOUT = 8 * 1024 * 1024
MAX_STDERR = 512 * 1024
DEFAULT_TIMEOUT = 120

TASK_NAME = "ARD-Host-Agent"


def app_dir() -> Path:
    """打包成 exe 后用 exe 所在目录, 源码运行用脚本目录。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def self_path() -> str:
    """当前可执行体路径: 打包后是 exe, 源码运行是 python 解释器。"""
    if getattr(sys, "frozen", False):
        return sys.executable
    return f'"{sys.executable}" "{Path(__file__).resolve()}"'


CONFIG_PATH = app_dir() / "agent.config.json"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def load_config() -> dict:
    cfg = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            log(f"读取配置文件失败, 忽略: {exc}")
    return cfg


def stable_device_id() -> str:
    """生成稳定的 host device_id, 跨重启不变。优先用机器名, 兜底用 MAC。"""
    host = socket.gethostname() or "pc"
    safe = "".join(c for c in host if c.isalnum() or c in "-_") or "pc"
    return f"host-{safe.lower()}"


def find_tool(name: str, configured: str | None) -> str:
    """定位 adb/fastboot: 配置 > PATH > 常见 SDK 路径。找不到则原样返回工具名。"""
    if configured and Path(configured).exists():
        return configured
    found = shutil.which(name)
    if found:
        return found
    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / f"{name}.exe",
        Path(os.environ.get("ANDROID_HOME", "")) / "platform-tools" / f"{name}.exe",
        Path(os.environ.get("ANDROID_SDK_ROOT", "")) / "platform-tools" / f"{name}.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return name


class HostAgent:
    def __init__(self, relay_ws: str, token: str, device_id: str, name: str,
                 adb_path: str, fastboot_path: str):
        self.relay_ws = relay_ws.rstrip("/")
        self.token = token
        self.device_id = device_id
        self.name = name
        self.adb_path = adb_path
        self.fastboot_path = fastboot_path

    def url(self) -> str:
        return f"{self.relay_ws}/{self.device_id}"

    async def run(self) -> None:
        log(f"Host Agent 启动: device_id={self.device_id} name={self.name}")
        log(f"adb={self.adb_path}")
        log(f"fastboot={self.fastboot_path}")
        log(f"Relay={self.relay_ws}")
        while True:
            try:
                await self._connect_once()
            except Exception as exc:  # noqa: BLE001 - agent 必须永不退出
                log(f"连接异常: {exc!r}")
            log(f"{RECONNECT_DELAY_SECONDS}s 后重连...")
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)

    async def _connect_once(self) -> None:
        async with websockets.connect(self.url(), additional_headers={"Authorization": f"Bearer {self.token}"},
                                       ping_interval=20, ping_timeout=20,
                                       max_size=None, open_timeout=15) as ws:
            log("WebSocket 已连接")
            await self._send_hello(ws)
            hb = asyncio.create_task(self._heartbeat(ws))
            try:
                async for raw in ws:
                    await self._on_message(ws, raw)
            finally:
                hb.cancel()

    async def _send_hello(self, ws) -> None:
        await ws.send(json.dumps({
            "type": "hello",
            "name": self.name,
            "model": f"PC/{platform.system()}",
            "androidVersion": platform.platform(),
            "root": True,  # PC 端默认有完整权限
        }))

    async def _heartbeat(self, ws) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                await ws.send(json.dumps({"type": "heartbeat"}))
        except asyncio.CancelledError:
            pass

    async def _on_message(self, ws, raw: str) -> None:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return
        if msg.get("type") != "command":
            return
        request_id = msg.get("requestId", "")
        action = msg.get("action", "")
        args = msg.get("args") or {}
        # 异步执行, 不阻塞接收循环
        asyncio.create_task(self._dispatch(ws, request_id, action, args))

    async def _dispatch(self, ws, request_id: str, action: str, args: dict) -> None:
        started = time.time()
        try:
            exit_code, stdout, stderr = await self._handle(action, args)
            status = "ok"
        except Exception as exc:  # noqa: BLE001
            exit_code, stdout, stderr, status = 1, "", repr(exc), "error"
        duration = int((time.time() - started) * 1000)
        await ws.send(json.dumps({
            "type": "result",
            "requestId": request_id,
            "status": status,
            "exitCode": exit_code,
            "stdout": stdout[:MAX_STDOUT],
            "stderr": stderr[:MAX_STDERR],
            "durationMs": duration,
        }))

    async def _handle(self, action: str, args: dict):
        if action == "host.which":
            return self._which()
        if action == "host.exec":
            return await self._exec(args.get("command", ""),
                                    timeout=int(args.get("timeoutSeconds", DEFAULT_TIMEOUT)))
        if action == "host.adb":
            return await self._exec_tool(self.adb_path, args)
        if action == "host.fastboot":
            return await self._exec_tool(self.fastboot_path, args)
        if action == "device.info":
            # 兼容 ard device <id> info
            code, out, err = self._which()
            return code, out, err
        return 2, "", f"unknown action: {action}"

    def _which(self):
        info = {
            "name": self.name,
            "hostname": socket.gethostname(),
            "loginUser": os.getenv("USERNAME") or os.getenv("USER") or "",
            "platform": platform.platform(),
            "adb": self.adb_path,
            "fastboot": self.fastboot_path,
        }
        for key, path in (("adbVersion", self.adb_path), ("fastbootVersion", self.fastboot_path)):
            try:
                out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10)
                info[key] = (out.stdout or out.stderr).strip().splitlines()[:1]
            except Exception as exc:  # noqa: BLE001
                info[key] = f"error: {exc}"
        return 0, json.dumps(info, ensure_ascii=False, indent=2), ""

    async def _exec_tool(self, tool: str, args: dict):
        """host.adb / host.fastboot: tool 后接 args.args(数组)或 args.command(字符串)。"""
        timeout = int(args.get("timeoutSeconds", DEFAULT_TIMEOUT))
        if isinstance(args.get("args"), list):
            argv = [tool] + [str(a) for a in args["args"]]
            return await self._exec_argv(argv, timeout)
        suffix = str(args.get("command", "")).strip()
        cmd = f'"{tool}" {suffix}' if suffix else f'"{tool}"'
        return await self._exec(cmd, timeout)

    async def _exec(self, command: str, timeout: int):
        if not command.strip():
            return 2, "", "empty command"
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await self._collect(proc, timeout, command)

    async def _exec_argv(self, argv: list, timeout: int):
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        return await self._collect(proc, timeout, " ".join(argv))

    async def _collect(self, proc, timeout: int, label: str):
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return 124, "", f"command timed out after {timeout}s: {label}"
        return (
            proc.returncode if proc.returncode is not None else -1,
            out.decode("utf-8", errors="replace"),
            err.decode("utf-8", errors="replace"),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Android Remote Debug - PC Host Agent")
    parser.add_argument("--relay", help="Relay WS 基址, 形如 ws://host:port/ws/mobile")
    parser.add_argument("--token", help="API token")
    parser.add_argument("--device-id", help="本机 host 设备 id (默认按机器名生成, 稳定)")
    parser.add_argument("--name", help="显示名称")
    parser.add_argument("--adb", help="adb 可执行文件路径")
    parser.add_argument("--fastboot", help="fastboot 可执行文件路径")
    parser.add_argument("--run", action="store_true",
                        help="直接进入 agent 主循环(供计划任务调用), 不走一键安装")
    parser.add_argument("--install", action="store_true",
                        help="安装开机自启计划任务并立即后台运行")
    parser.add_argument("--uninstall", action="store_true",
                        help="卸载开机自启计划任务并停止")
    return parser


def resolve_settings(args):
    cfg = load_config()
    relay = (args.relay or os.getenv("ARD_RELAY_WS") or cfg.get("relay_ws") or DEFAULT_RELAY_WS)
    token = (args.token or os.getenv("ARD_API_TOKEN") or cfg.get("token") or DEFAULT_TOKEN)
    device_id = (args.device_id or os.getenv("ARD_HOST_ID") or cfg.get("device_id") or stable_device_id())
    name = (args.name or os.getenv("ARD_HOST_NAME") or cfg.get("name") or f"PC-{socket.gethostname()}")
    adb_path = find_tool("adb", args.adb or cfg.get("adb"))
    fastboot_path = find_tool("fastboot", args.fastboot or cfg.get("fastboot"))
    return relay, token, device_id, name, adb_path, fastboot_path


def settings_error(relay: str, token: str, device_id: str) -> str | None:
    if not relay.startswith(("ws://", "wss://")):
        return "Relay 地址必须以 ws:// 或 wss:// 开头"
    if len(token) < 32 or token == "replace-with-relay-token":
        return "请通过配置文件或 ARD_API_TOKEN 设置至少 32 个字符的随机 token"
    if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", device_id) is None:
        return "device_id 只能包含 ASCII 字母、数字、连字符和下划线，且最长 128 个字符"
    return None


def main() -> None:
    args = build_parser().parse_args()

    if args.uninstall:
        do_uninstall()
        return
    if args.install:
        do_install()
        return
    if args.run:
        run_agent(args)
        return

    # 无参数 = 双击运行: 一键安装(首次) 或 提示已运行(再次)
    interactive_setup()


def run_agent(args) -> None:
    relay, token, device_id, name, adb_path, fastboot_path = resolve_settings(args)
    error = settings_error(relay, token, device_id)
    if error:
        raise SystemExit(error)
    agent = HostAgent(relay, token, device_id, name, adb_path, fastboot_path)
    try:
        asyncio.run(agent.run())
    except KeyboardInterrupt:
        log("已退出")


# ---------------------------------------------------------------------------
# 一键安装 / 自启 (仅 Windows)
# ---------------------------------------------------------------------------

def _is_windows() -> bool:
    return os.name == "nt"


def _is_admin() -> bool:
    if not _is_windows():
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:  # noqa: BLE001
        return False


def _relaunch_as_admin(extra_args: str) -> bool:
    """以管理员重新启动自身并执行 extra_args。返回是否成功发起提权。"""
    if not _is_windows():
        return False
    import ctypes
    try:
        if getattr(sys, "frozen", False):
            exe, params = sys.executable, extra_args
        else:
            exe = sys.executable
            params = f'"{Path(__file__).resolve()}" {extra_args}'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return int(rc) > 32
    except Exception as exc:  # noqa: BLE001
        log(f"提权失败: {exc}")
        return False


def _task_exists() -> bool:
    try:
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                           capture_output=True, text=True)
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def save_name_to_config(name: str) -> None:
    """把客户填的名字写进 agent.config.json, 供 --run(SYSTEM) 读取。"""
    cfg = load_config()
    cfg["name"] = name
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError as exc:
        log(f"写配置失败: {exc}")


def ask_name_gui(default: str) -> str:
    """弹输入框让客户给这台电脑起名(认领是哪个客户)。失败则退回控制台输入。"""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        val = simpledialog.askstring(
            "远程协助助手 - 设备命名",
            "请给这台电脑起个名字(方便技术支持识别):\n例如  张三-仓库电脑",
            initialvalue=default,
            parent=root,
        )
        root.destroy()
        if val and val.strip():
            return val.strip()
    except Exception:  # noqa: BLE001
        pass
    return _ask(f"请给这台电脑起个名字 [默认 {default}]: ", default)


def do_install() -> None:
    """注册开机自启计划任务并立即启动(需管理员)。"""
    if not _is_windows():
        print("一键安装仅支持 Windows。其它平台请用 --run 直接运行。")
        return
    relay, token, device_id, _, _, _ = resolve_settings(build_parser().parse_args([]))
    error = settings_error(relay, token, device_id)
    if error:
        print(f"配置无效: {error}")
        print(f"请先编辑 {CONFIG_PATH}")
        _pause()
        return
    if not _is_admin():
        print("需要管理员权限来创建开机自启, 正在请求提权...")
        if not _relaunch_as_admin("--install"):
            print("提权被取消, 安装中止。")
            _pause()
        return

    run_cmd = f'{self_path()} --run'
    print(f"创建开机自启计划任务: {TASK_NAME}")
    create = subprocess.run([
        "schtasks", "/Create", "/TN", TASK_NAME, "/TR", run_cmd,
        "/SC", "ONSTART", "/RU", "SYSTEM", "/RL", "HIGHEST", "/F",
    ], capture_output=True, text=True)
    if create.returncode != 0:
        print("创建计划任务失败:")
        print(create.stdout or "", create.stderr or "")
        _pause()
        return

    subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, text=True)
    print()
    cfg = load_config()
    print(f"✅ 安装完成: 已设为开机自启并在后台启动。")
    print(f"   本机名称: {cfg.get('name') or '(未命名)'}")
    print(f"   卸载: 双击运行并选择卸载, 或 schtasks /Delete /TN {TASK_NAME} /F")
    _pause()


def do_uninstall() -> None:
    if not _is_windows():
        print("仅支持 Windows。")
        return
    if not _is_admin():
        print("需要管理员权限来卸载, 正在请求提权...")
        if not _relaunch_as_admin("--uninstall"):
            print("提权被取消。")
            _pause()
        return
    subprocess.run(["schtasks", "/End", "/TN", TASK_NAME], capture_output=True, text=True)
    subprocess.run(["schtasks", "/Delete", "/TN", TASK_NAME, "/F"], capture_output=True, text=True)
    if getattr(sys, "frozen", False):
        exe_name = Path(sys.executable).name
        subprocess.run(["taskkill", "/IM", exe_name, "/F"], capture_output=True, text=True)
    print("✅ 已卸载开机自启并停止运行。")
    _pause()


def interactive_setup() -> None:
    """双击运行的入口: 已安装则给状态, 未安装则一键安装。"""
    if not _is_windows():
        # 非 Windows 直接前台运行
        run_agent(build_parser().parse_args(["--run"]))
        return

    installed = _task_exists()
    print("=" * 48)
    print("  远程协助助手 (PC Host Agent)")
    print("=" * 48)
    if installed:
        print("状态: 已安装开机自启。")
        print()
        print("  [1] 重新启动后台服务")
        print("  [2] 卸载 (停止并取消开机自启)")
        print("  [3] 退出")
        choice = _ask("请选择 [1/2/3]: ", "1")
        if choice == "2":
            do_uninstall()
        elif choice == "1":
            subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], capture_output=True, text=True)
            print("已重新启动后台服务。")
            _pause()
        else:
            return
    else:
        print("首次运行, 将安装为开机自启后台服务。")
        # 在用户态(提权前)收集名字并写入配置, 之后 --run(SYSTEM) 才能读到
        cfg = load_config()
        default_name = cfg.get("name") or f"PC-{socket.gethostname()}"
        name = ask_name_gui(default_name)
        save_name_to_config(name)
        print(f"本机名称: {name}")
        do_install()


def _ask(prompt: str, default: str) -> str:
    try:
        v = input(prompt).strip()
        return v or default
    except (EOFError, KeyboardInterrupt):
        return default


def _pause() -> None:
    try:
        input("\n按回车关闭...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
