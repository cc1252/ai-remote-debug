"""Android Remote Debug MCP Server

MCP 客户端通过此 server 直接调用 ard.py 的后端 Relay API。
工具定义是固定 schema，会被提示缓存，不会每次重新加载。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

BASE_URL = os.getenv("ARD_RELAY_URL", "http://127.0.0.1:8000")
TOKEN = os.getenv("ARD_API_TOKEN", "")

# Cloudflare 等 CDN 会按 UA 拦截 Python-urllib 默认标识, 统一换成固定 UA
_opener = urllib.request.build_opener()
_opener.addheaders = [("User-Agent", "ard-mcp/0.2")]
urllib.request.install_opener(_opener)

mcp = FastMCP("ard")


# ---------------------------------------------------------------------------
# Relay helpers (mirrors ard.py)
# ---------------------------------------------------------------------------

def _api(method: str, path: str, body: dict | None = None, timeout: int = 90):
    url = BASE_URL.rstrip("/") + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = resp.read().decode()
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        return {"error": f"HTTP {e.code}", "detail": detail}
    except urllib.error.URLError as e:
        return {"error": "connect", "detail": str(e.reason)}


def _cmd(device: str, action: str, args: dict | None = None, wait: bool = True) -> dict:
    query = "?wait=true" if wait else "?wait=false"
    return _api("POST", f"/api/devices/{urllib.parse.quote(device)}/commands{query}", {
        "action": action, "args": args or {}})


def _resolve(selector: str) -> dict:
    """Return {"device_id": "...", ...} or {"error": ...}."""
    devices = (_api("GET", "/api/devices") or [])
    if isinstance(devices, dict) and "error" in devices:
        return devices
    if not devices:
        return {"error": "no devices registered on Relay"}
    sel = selector.lower()

    # exact device_id
    for d in devices:
        if d["device_id"] == selector:
            return {"device_id": d["device_id"]}
    # exact name
    name_exact = [d for d in devices if (d.get("name") or "").lower() == sel]
    if len(name_exact) == 1:
        return {"device_id": name_exact[0]["device_id"]}
    if len(name_exact) > 1:
        online = [d for d in name_exact if d.get("online")]
        if len(online) == 1:
            return {"device_id": online[0]["device_id"]}
    # name substring
    name_sub = [d for d in devices if sel in (d.get("name") or "").lower()]
    if len(name_sub) == 1:
        return {"device_id": name_sub[0]["device_id"]}
    if len(name_sub) > 1:
        online = [d for d in name_sub if d.get("online")]
        if len(online) == 1:
            return {"device_id": online[0]["device_id"]}
    # id prefix
    id_pre = [d for d in devices if d["device_id"].startswith(selector)]
    if len(id_pre) == 1:
        return {"device_id": id_pre[0]["device_id"]}
    if len(id_pre) > 1:
        online = [d for d in id_pre if d.get("online")]
        if len(online) == 1:
            return {"device_id": online[0]["device_id"]}
    # fallback: return list
    return {"error": f"ambiguous", "candidates": [
        {"device_id": d["device_id"], "name": d.get("name", ""), "online": d.get("online")}
        for d in devices]}


def _resolve_one(selector: str) -> str:
    r = _resolve(selector)
    if "error" in r:
        if "candidates" in r:
            names = "\n".join(f"  {c['device_id']} name={c.get('name','')} online={c.get('online')}"
                              for c in r["candidates"])
            return f"device_not_found: 请重选设备。候选：\n{names}"
        return f"device_not_found: {r['error']}"
    return r["device_id"]


# ---------------------------------------------------------------------------
# MCP tools – each is a fixed function signature = caching friendly
# ---------------------------------------------------------------------------

@mcp.tool()
def list_devices() -> str:
    """列出 Relay 上所有注册的设备，包括在线状态、型号、root 状态。"""
    devices = _api("GET", "/api/devices") or []
    if isinstance(devices, dict) and "error" in devices:
        return json.dumps(devices, ensure_ascii=False)
    summary = []
    for d in devices:
        summary.append({
            "device_id": d["device_id"],
            "name": d.get("name", ""),
            "model": d.get("model", ""),
            "android_version": d.get("android_version", ""),
            "root": d.get("root", False),
            "online": d.get("online", False),
            "last_seen_seconds_ago": round(time.time() - d.get("last_seen", 0), 0),
        })
    return json.dumps(summary, ensure_ascii=False, indent=2)


@mcp.tool()
def get_device_info(device: str) -> str:
    """获取设备详细信息：型号、厂商、Android 版本、SDK 版本、root 状态。

    Args:
        device: 设备名、device_id 或唯一前缀。例如 'a1' 或 'ca1f'
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "device.info")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def run_shell(device: str, command: str, use_root: bool = True, timeout_seconds: int = 30) -> str:
    """在手机上执行任意 shell 命令（类似 adb shell）。

    Args:
        device: 设备名或 device_id
        command: 要执行的 shell 命令。支持 &&、管道、分号
        use_root: 是否用 root 执行。手机无 root 时设为 false
        timeout_seconds: 超时秒数
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "shell.exec", {
        "command": command,
        "root": use_root,
        "timeoutSeconds": timeout_seconds,
    })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def dump_logcat(device: str, lines: int = 500, tag: str = "", level: str = "") -> str:
    """拉取 logcat 日志。

    Args:
        device: 设备名或 device_id
        lines: 拉取行数，默认 500
        tag: 按 tag 过滤
        level: 日志级别过滤 V/D/I/W/E/F
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "logcat.dump", {"lines": lines, "tag": tag, "level": level})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def list_apps(device: str) -> str:
    """列出手机上已安装的应用包名（pm list packages）。

    Args:
        device: 设备名或 device_id
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "app.list")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def start_app(device: str, component: str) -> str:
    """启动一个应用。

    Args:
        device: 设备名或 device_id
        component: 组件名，例如 com.example/.MainActivity
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "app.start", {"component": component})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def stop_app(device: str, package_name: str) -> str:
    """强制停止一个应用。

    Args:
        device: 设备名或 device_id
        package_name: 应用包名
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "app.stop", {"packageName": package_name})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def clear_app_data(device: str, package_name: str) -> str:
    """清除应用数据（危险操作，会删除该应用本地数据）。

    Args:
        device: 设备名或 device_id
        package_name: 应用包名
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "app.clearData", {"packageName": package_name})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def dumpsys_app(device: str, package_name: str) -> str:
    """查询应用的 dumpsys 信息。

    Args:
        device: 设备名或 device_id
        package_name: 应用包名或服务名
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "app.dumpsys", {"packageName": package_name})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def input_keyevent(device: str, key: str) -> str:
    """向手机发送按键事件（类似 adb shell input keyevent）。

    Args:
        device: 设备名或 device_id
        key: 按键名，例如 HOME, BACK, KEYCODE_APP_SWITCH, KEYCODE_ENTER
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "input.keyevent", {"key": key})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def screencap(device: str, output_path: str = "screen.png") -> str:
    """截取手机屏幕并保存到本地文件。

    Args:
        device: 设备名或 device_id
        output_path: 本地保存路径，默认 screen.png
    """
    import base64
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "screen.cap")
    if result.get("exit_code") != 0:
        return json.dumps(result, ensure_ascii=False, indent=2)
    data = base64.b64decode("".join(result.get("stdout", "").split()))
    with open(output_path, "wb") as f:
        f.write(data)
    return json.dumps({"ok": True, "path": output_path, "size": len(data)}, ensure_ascii=False)


@mcp.tool()
def file_pull(device: str, remote_path: str, local_path: str) -> str:
    """从小手机拉取小文件到本地（base64 传输，适合 <1MB）。

    Args:
        device: 设备名或 device_id
        remote_path: 手机上的文件路径
        local_path: 本地保存路径
    """
    import base64
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "file.readBase64", {"path": remote_path, "timeoutSeconds": 60})
    if result.get("exit_code") != 0:
        return json.dumps(result, ensure_ascii=False, indent=2)
    data = base64.b64decode("".join(result.get("stdout", "").split()))
    with open(local_path, "wb") as f:
        f.write(data)
    return json.dumps({"ok": True, "path": local_path, "size": len(data)}, ensure_ascii=False)


@mcp.tool()
def file_push(device: str, local_path: str, remote_path: str) -> str:
    """上传小文件到手机（base64 传输，适合 <1MB）。

    Args:
        device: 设备名或 device_id
        local_path: 本地文件路径
        remote_path: 手机上的目标路径
    """
    import base64
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    with open(local_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    result = _cmd(did, "file.writeBase64", {"path": remote_path, "data": data, "timeoutSeconds": 60})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def install_apk(device: str, apk_path: str) -> str:
    """安装 APK 到手机。

    Args:
        device: 设备名或 device_id
        apk_path: 本地 APK 文件路径
    """
    import base64
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    with open(apk_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("ascii")
    remote = "/data/local/tmp/ard-install.apk"
    upload = _cmd(did, "file.writeBase64", {"path": remote, "data": data, "timeoutSeconds": 120})
    if upload.get("exit_code") != 0:
        return json.dumps(upload, ensure_ascii=False, indent=2)
    result = _cmd(did, "app.install", {"path": remote, "timeoutSeconds": 120})
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def adb_tcp_status(device: str) -> str:
    """查看 adb tcp 端口状态。

    Args:
        device: 设备名或 device_id
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "adb.tcp.status")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def host_exec(device: str, command: str, timeout_seconds: int = 120) -> str:
    """在客户电脑(PC host agent)上执行任意命令。

    用于通过客户的电脑控制其手机：adb / fastboot 救砖、刷机等，
    手机系统死机或进入 fastboot 时仍可操作。device 选 host 设备
    (名字通常以 PC- 开头，device_id 以 host- 开头)。

    Args:
        device: host 设备名或 device_id
        command: 在电脑上执行的命令行(shell)，如 'adb devices' 或 'fastboot reboot'
        timeout_seconds: 超时秒数
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "host.exec", {"command": command, "timeoutSeconds": timeout_seconds}, wait=True)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def host_adb(device: str, args: str, timeout_seconds: int = 120) -> str:
    """在客户电脑上执行 adb 命令(自动定位 adb 路径)。

    Args:
        device: host 设备名或 device_id
        args: adb 之后的参数，如 'devices' 或 'shell getprop ro.product.model'
        timeout_seconds: 超时秒数
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "host.adb", {"command": args, "timeoutSeconds": timeout_seconds}, wait=True)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def host_fastboot(device: str, args: str, timeout_seconds: int = 120) -> str:
    """在客户电脑上执行 fastboot 命令(自动定位 fastboot 路径)。

    Args:
        device: host 设备名或 device_id
        args: fastboot 之后的参数，如 'devices' 或 'reboot'
        timeout_seconds: 超时秒数
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "host.fastboot", {"command": args, "timeoutSeconds": timeout_seconds}, wait=True)
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def host_which(device: str) -> str:
    """查客户电脑上的 adb/fastboot 路径与版本(host agent 自检)。

    Args:
        device: host 设备名或 device_id
    """
    did = _resolve_one(device)
    if did.startswith("device_not_found"):
        return did
    result = _cmd(did, "host.which")
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    mcp.run(transport="stdio")
