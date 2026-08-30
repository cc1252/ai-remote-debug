#!/usr/bin/env python3
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.getenv("ARD_RELAY_URL", "http://127.0.0.1:8000")
TOKEN = os.getenv("ARD_API_TOKEN", "")

# Cloudflare 等 CDN 会按 UA 拦截 Python-urllib 默认标识, 统一换成固定 UA
_opener = urllib.request.build_opener()
_opener.addheaders = [("User-Agent", "ard-cli/0.2")]
urllib.request.install_opener(_opener)


def request(method: str, path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            payload = response.read().decode("utf-8")
            return json.loads(payload) if payload else None
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {error.code}: {detail}")
    except urllib.error.URLError as error:
        raise SystemExit(f"Relay request failed: {error}")


def upload_artifact(local_path: str, artifact_id: str | None = None):
    path = "/api/artifacts" if artifact_id is None else f"/api/artifacts/{urllib.parse.quote(artifact_id)}"
    with open(local_path, "rb") as file:
        data = file.read()
    req = urllib.request.Request(
        BASE_URL.rstrip("/") + path,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {error.code}: {detail}")


def download_artifact(artifact_id: str, local_path: str):
    url = f"{BASE_URL.rstrip('/')}/api/artifacts/{urllib.parse.quote(artifact_id)}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    started = time.time()
    size = 0
    try:
        with urllib.request.urlopen(req, timeout=600) as response, open(local_path, "wb") as file:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                file.write(chunk)
                size += len(chunk)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {error.code}: {detail}")
    elapsed = max(time.time() - started, 0.001)
    print(f"downloaded {size} bytes to {local_path} in {elapsed:.2f}s ({size / 1024 / 1024 / elapsed:.2f} MB/s)")


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def command(device_id: str, action: str, args: dict | None = None, wait: bool = True):
    query = "?wait=true" if wait else "?wait=false"
    return request("POST", f"/api/devices/{urllib.parse.quote(device_id)}/commands{query}", {
        "action": action,
        "args": args or {},
    })


def require_confirm(args, message: str):
    if not getattr(args, "confirm", False):
        raise SystemExit(f"{message}。如确认执行，请追加 --confirm")


def resolve_device(selector: str) -> str:
    """Accept a device_id, a name, or a unique id-prefix and return the real device_id.

    Resolution order: exact device_id > exact name (case-insensitive) >
    unique substring of name > unique device_id prefix. Prefers online devices
    when a name matches several. Raises SystemExit with the candidate list if
    the selector is ambiguous or matches nothing.
    """
    devices = request("GET", "/api/devices") or []
    if not devices:
        raise SystemExit("没有任何设备注册到 Relay。请在手机上点『一键启动远程调试』。")

    # 1. exact device_id
    for d in devices:
        if d["device_id"] == selector:
            return selector

    sel_lower = selector.lower()

    def pick(matches, how):
        online = [d for d in matches if d.get("online")]
        chosen = online if len(online) == 1 else matches
        if len(chosen) == 1:
            return chosen[0]["device_id"]
        listing = "\n".join(
            f"  {d['device_id']}  name={d.get('name')!r}  online={d.get('online')}" for d in matches
        )
        raise SystemExit(f"设备选择 {selector!r} ({how}) 匹配到多台，请用更精确的名字或完整 device_id：\n{listing}")

    # 2. exact name
    name_exact = [d for d in devices if (d.get("name") or "").lower() == sel_lower]
    if name_exact:
        return pick(name_exact, "按名字精确匹配")

    # 3. name substring
    name_sub = [d for d in devices if sel_lower in (d.get("name") or "").lower()]
    if name_sub:
        return pick(name_sub, "按名字包含匹配")

    # 4. device_id prefix
    id_prefix = [d for d in devices if d["device_id"].startswith(selector)]
    if id_prefix:
        return pick(id_prefix, "按 device_id 前缀匹配")

    listing = "\n".join(
        f"  {d['device_id']}  name={d.get('name')!r}  online={d.get('online')}" for d in devices
    )
    raise SystemExit(f"找不到匹配 {selector!r} 的设备。当前设备：\n{listing}")


def main():
    parser = argparse.ArgumentParser(prog="ard", description="Remote Android debug CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("devices")

    device = sub.add_parser("device")
    device.add_argument("device_id")
    device.add_argument("field", choices=["info"])

    logcat = sub.add_parser("logcat")
    logcat.add_argument("device_id")
    logcat.add_argument("--tag")
    logcat.add_argument("--level")
    logcat.add_argument("--lines", type=int, default=1000)

    sub.add_parser("help-actions")

    app_list = sub.add_parser("app-list")
    app_list.add_argument("device_id")

    app_start = sub.add_parser("app-start")
    app_start.add_argument("device_id")
    app_start.add_argument("component")

    app_stop = sub.add_parser("app-stop")
    app_stop.add_argument("device_id")
    app_stop.add_argument("package_name")

    app_clear = sub.add_parser("app-clear")
    app_clear.add_argument("device_id")
    app_clear.add_argument("package_name")
    app_clear.add_argument("--confirm", action="store_true")

    dumpsys = sub.add_parser("dumpsys")
    dumpsys.add_argument("device_id")
    dumpsys.add_argument("package_name")

    input_key = sub.add_parser("input-key")
    input_key.add_argument("device_id")
    input_key.add_argument("key")

    adb_tcp = sub.add_parser("adb-tcp")
    adb_tcp.add_argument("device_id")
    adb_tcp.add_argument("state", choices=["status", "enable", "disable"])
    adb_tcp.add_argument("--confirm", action="store_true")

    shell = sub.add_parser("shell")
    shell.add_argument("device_id")
    shell.add_argument("command")
    shell.add_argument("--no-root", action="store_true")
    shell.add_argument("--timeout", type=int, default=30)
    shell.add_argument("--confirm", action="store_true")

    pull = sub.add_parser("pull")
    pull.add_argument("device_id")
    pull.add_argument("remote_path")
    pull.add_argument("local_path")
    pull.add_argument("--timeout", type=int, default=60)

    push = sub.add_parser("push")
    push.add_argument("device_id")
    push.add_argument("local_path")
    push.add_argument("remote_path")
    push.add_argument("--timeout", type=int, default=60)
    push.add_argument("--confirm", action="store_true")

    install = sub.add_parser("install")
    install.add_argument("device_id")
    install.add_argument("apk_path")
    install.add_argument("--remote-path", default="/data/local/tmp/ard-install.apk")
    install.add_argument("--confirm", action="store_true")

    screencap = sub.add_parser("screencap")
    screencap.add_argument("device_id")
    screencap.add_argument("local_path")

    pull_big = sub.add_parser("pull-big")
    pull_big.add_argument("device_id")
    pull_big.add_argument("remote_path")
    pull_big.add_argument("local_path")
    pull_big.add_argument("--chunk-size", type=int, default=512 * 1024)

    push_big = sub.add_parser("push-big")
    push_big.add_argument("device_id")
    push_big.add_argument("local_path")
    push_big.add_argument("remote_path")
    push_big.add_argument("--chunk-size", type=int, default=512 * 1024)
    push_big.add_argument("--confirm", action="store_true")

    push_fast = sub.add_parser("push-fast")
    push_fast.add_argument("device_id")
    push_fast.add_argument("local_path")
    push_fast.add_argument("remote_path")
    push_fast.add_argument("--confirm", action="store_true")

    pull_fast = sub.add_parser("pull-fast")
    pull_fast.add_argument("device_id")
    pull_fast.add_argument("remote_path")
    pull_fast.add_argument("local_path")

    # ---- PC host agent (装在客户电脑上, 远程跑 adb/fastboot/任意命令) ----
    host_exec = sub.add_parser("host-exec", help="在 host 电脑上执行任意命令")
    host_exec.add_argument("device_id")
    host_exec.add_argument("command")
    host_exec.add_argument("--timeout", type=int, default=120)
    host_exec.add_argument("--confirm", action="store_true")

    host_adb = sub.add_parser("host-adb", help="在 host 电脑上执行 adb 命令")
    host_adb.add_argument("device_id")
    host_adb.add_argument("args", nargs=argparse.REMAINDER, help="adb 之后的参数")
    host_adb.add_argument("--timeout", type=int, default=120)

    host_fastboot = sub.add_parser("host-fastboot", help="在 host 电脑上执行 fastboot 命令")
    host_fastboot.add_argument("device_id")
    host_fastboot.add_argument("args", nargs=argparse.REMAINDER, help="fastboot 之后的参数")
    host_fastboot.add_argument("--timeout", type=int, default=120)

    host_which = sub.add_parser("host-which", help="查 host 电脑上的 adb/fastboot 路径与版本")
    host_which.add_argument("device_id")

    args = parser.parse_args()
    if not TOKEN:
        raise SystemExit("请先设置 ARD_API_TOKEN 环境变量")

    # 允许用设备名 / id前缀代替完整 device_id（devices 命令本身不需要）
    if getattr(args, "device_id", None):
        args.device_id = resolve_device(args.device_id)

    if args.cmd == "devices":
        print_json(request("GET", "/api/devices"))
    elif args.cmd == "device":
        result = command(args.device_id, "device.info") if args.field == "info" else None
        print_json(result)
    elif args.cmd == "logcat":
        print_json(command(args.device_id, "logcat.dump", {
            "tag": args.tag or "",
            "level": args.level or "",
            "lines": args.lines,
        }))
    elif args.cmd == "help-actions":
        print("device.info, logcat.dump, app.list, app.start, app.stop, app.clearData, app.dumpsys, input.keyevent, adb.tcp.status, adb.tcp.enable, adb.tcp.disable, shell.exec")
    elif args.cmd == "app-list":
        print_json(command(args.device_id, "app.list"))
    elif args.cmd == "app-start":
        print_json(command(args.device_id, "app.start", {"component": args.component}))
    elif args.cmd == "app-stop":
        print_json(command(args.device_id, "app.stop", {"packageName": args.package_name}))
    elif args.cmd == "app-clear":
        require_confirm(args, "清除应用数据会删除该应用本地数据")
        print_json(command(args.device_id, "app.clearData", {"packageName": args.package_name}))
    elif args.cmd == "dumpsys":
        print_json(command(args.device_id, "app.dumpsys", {"packageName": args.package_name}))
    elif args.cmd == "input-key":
        print_json(command(args.device_id, "input.keyevent", {"key": args.key}))
    elif args.cmd == "adb-tcp":
        action = f"adb.tcp.{args.state}"
        if args.state in {"enable", "disable"}:
            require_confirm(args, "修改 adbd tcp 状态会重启 adbd")
        print_json(command(args.device_id, action))
    elif args.cmd == "shell":
        require_confirm(args, "执行任意 shell 命令")
        print_json(command(args.device_id, "shell.exec", {
            "command": args.command,
            "root": not args.no_root,
            "timeoutSeconds": args.timeout,
        }))
    elif args.cmd == "pull":
        result = command(args.device_id, "file.readBase64", {
            "path": args.remote_path,
            "timeoutSeconds": args.timeout,
        })
        if result.get("exit_code") != 0:
            print_json(result)
            raise SystemExit(result.get("exit_code", 1) or 1)
        data = base64.b64decode("".join(result.get("stdout", "").split()))
        with open(args.local_path, "wb") as file:
            file.write(data)
        print(f"wrote {len(data)} bytes to {args.local_path}")
    elif args.cmd == "push":
        require_confirm(args, "上传文件会覆盖远端路径")
        with open(args.local_path, "rb") as file:
            data = base64.b64encode(file.read()).decode("ascii")
        print_json(command(args.device_id, "file.writeBase64", {
            "path": args.remote_path,
            "data": data,
            "timeoutSeconds": args.timeout,
        }))
    elif args.cmd == "install":
        require_confirm(args, "安装 APK 会修改手机应用")
        with open(args.apk_path, "rb") as file:
            data = base64.b64encode(file.read()).decode("ascii")
        upload = command(args.device_id, "file.writeBase64", {
            "path": args.remote_path,
            "data": data,
            "timeoutSeconds": 120,
        })
        if upload.get("exit_code") != 0:
            print_json(upload)
            raise SystemExit(upload.get("exit_code", 1) or 1)
        print_json(command(args.device_id, "app.install", {
            "path": args.remote_path,
            "timeoutSeconds": 120,
        }))
    elif args.cmd == "screencap":
        result = command(args.device_id, "screen.cap")
        if result.get("exit_code") != 0:
            print_json(result)
            raise SystemExit(result.get("exit_code", 1) or 1)
        data = base64.b64decode("".join(result.get("stdout", "").split()))
        with open(args.local_path, "wb") as file:
            file.write(data)
        print(f"wrote {len(data)} bytes to {args.local_path}")
    elif args.cmd == "pull-big":
        size_result = command(args.device_id, "file.size", {"path": args.remote_path})
        if size_result.get("exit_code") != 0:
            print_json(size_result)
            raise SystemExit(size_result.get("exit_code", 1) or 1)
        total = int(size_result.get("stdout", "0").strip() or "0")
        started = time.time()
        written = 0
        with open(args.local_path, "wb") as file:
            while written < total:
                result = command(args.device_id, "file.readChunkBase64", {
                    "path": args.remote_path,
                    "offset": written,
                    "size": args.chunk_size,
                    "timeoutSeconds": 60,
                })
                if result.get("exit_code") != 0:
                    print_json(result)
                    raise SystemExit(result.get("exit_code", 1) or 1)
                data = base64.b64decode("".join(result.get("stdout", "").split()))
                if not data:
                    break
                file.write(data)
                written += len(data)
                print(f"\r{written}/{total} bytes", end="", flush=True)
        elapsed = max(time.time() - started, 0.001)
        print(f"\nwrote {written} bytes to {args.local_path} in {elapsed:.2f}s ({written / 1024 / 1024 / elapsed:.2f} MB/s)")
    elif args.cmd == "push-big":
        require_confirm(args, "分片上传文件会覆盖远端路径")
        total = os.path.getsize(args.local_path)
        started = time.time()
        sent = 0
        first = True
        with open(args.local_path, "rb") as file:
            while True:
                chunk = file.read(args.chunk_size)
                if not chunk:
                    break
                result = command(args.device_id, "file.writeChunkBase64", {
                    "path": args.remote_path,
                    "data": base64.b64encode(chunk).decode("ascii"),
                    "append": not first,
                    "timeoutSeconds": 60,
                })
                if result.get("exit_code") != 0:
                    print_json(result)
                    raise SystemExit(result.get("exit_code", 1) or 1)
                first = False
                sent += len(chunk)
                print(f"\r{sent}/{total} bytes", end="", flush=True)
        elapsed = max(time.time() - started, 0.001)
        print(f"\nwrote {sent} bytes to {args.remote_path} in {elapsed:.2f}s ({sent / 1024 / 1024 / elapsed:.2f} MB/s)")
    elif args.cmd == "push-fast":
        require_confirm(args, "快速上传文件会覆盖远端路径")
        started = time.time()
        artifact = upload_artifact(args.local_path)
        uploaded = artifact.get("size", os.path.getsize(args.local_path))
        upload_elapsed = max(time.time() - started, 0.001)
        result = command(args.device_id, "artifact.downloadToFile", {
            "baseUrl": BASE_URL,
            "token": TOKEN,
            "artifactId": artifact["artifact_id"],
            "path": args.remote_path,
            "timeoutSeconds": 300,
        })
        print_json(result)
        total_elapsed = max(time.time() - started, 0.001)
        print(f"uploaded {uploaded} bytes via artifact {artifact['artifact_id']} in {total_elapsed:.2f}s ({uploaded / 1024 / 1024 / total_elapsed:.2f} MB/s)")
    elif args.cmd == "pull-fast":
        artifact_id = f"pull-{args.device_id}-{int(time.time() * 1000)}"
        started = time.time()
        result = command(args.device_id, "artifact.uploadFromFile", {
            "baseUrl": BASE_URL,
            "token": TOKEN,
            "artifactId": artifact_id,
            "path": args.remote_path,
            "timeoutSeconds": 300,
        })
        if result.get("exit_code") != 0:
            print_json(result)
            raise SystemExit(result.get("exit_code", 1) or 1)
        download_artifact(artifact_id, args.local_path)
        elapsed = max(time.time() - started, 0.001)
        size = os.path.getsize(args.local_path)
        print(f"pulled {size} bytes from {args.remote_path} in {elapsed:.2f}s ({size / 1024 / 1024 / elapsed:.2f} MB/s)")
    elif args.cmd == "host-exec":
        require_confirm(args, "host-exec 会在远程电脑上执行任意命令")
        print_json(command(args.device_id, "host.exec", {
            "command": args.command,
            "timeoutSeconds": args.timeout,
        }))
    elif args.cmd == "host-adb":
        print_json(command(args.device_id, "host.adb", {
            "args": args.args,
            "timeoutSeconds": args.timeout,
        }))
    elif args.cmd == "host-fastboot":
        print_json(command(args.device_id, "host.fastboot", {
            "args": args.args,
            "timeoutSeconds": args.timeout,
        }))
    elif args.cmd == "host-which":
        print_json(command(args.device_id, "host.which"))


if __name__ == "__main__":
    main()
