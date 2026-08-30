# PC Host Agent — 通过客户电脑远程控制其手机

装在**客户电脑**上的常驻 agent。它连到 Relay 后注册成一个 `host` 设备，
你可以通过 CLI 或 MCP 远程让这台电脑执行 `adb` / `fastboot` / 任意命令——
即使客户手机系统死机、黑砖、或进了 fastboot/recovery，只要 USB 连着电脑就能救。

跟手机端 App 完全独立，互不依赖。

## 组成

| 文件 | 作用 |
|---|---|
| `agent.py` | agent 主程序（Python） |
| `agent.config.example.json` | 配置模板，复制成 `agent.config.json` 使用 |
| `build.bat` | 在开发机上把 agent 打包成单文件 exe |
| `install-autostart.bat` | 在客户电脑上装开机自启（计划任务） |
| `uninstall-autostart.bat` | 卸载自启并停止 |

## 工作原理

agent 复用手机端同一套 Relay WebSocket 协议（`/ws/mobile/{device_id}`），
作为一个 `device_id` 以 `host-` 开头的设备上线。收到命令后在本机执行：

| action | 说明 |
|---|---|
| `host.exec` | 在电脑上执行任意命令行（shell） |
| `host.adb` | 自动定位 adb，执行 `adb <args>` |
| `host.fastboot` | 自动定位 fastboot，执行 `fastboot <args>` |
| `host.which` | 返回 adb/fastboot 路径与版本（自检） |

> 安全说明：agent 接受任意命令执行，等于把这台电脑的控制权交给持有 token 的人。
> token 即权限，务必只在受信任的 Relay 和环境里使用。

## 客户怎么安装

把预配置好的 `ard-host-agent.exe` 发给客户。客户只需要：

1. 双击 EXE；
2. 填写一个便于技术支持识别的电脑名称；
3. 同意 Windows 管理员授权。

程序会自动创建开机自启任务并立即上线。客户不需要安装 Python、不需要编辑 JSON，也不需要运行 BAT 文件。再次双击同一个 EXE，可以重新启动后台服务或卸载。

## 维护者怎么制作客户版 EXE

在开发机执行：

```powershell
python -m venv .build-venv
.\.build-venv\Scripts\pip install -r requirements.txt pyinstaller

$env:ARD_API_TOKEN = "<与 Relay 相同的至少 32 字符 token>"
.\build-customer.ps1 -RelayWs "wss://relay.example.com/ws/mobile"
Remove-Item Env:\ARD_API_TOKEN
```

产物位于 `release\ard-host-agent.exe`。脚本临时生成注入连接参数的源码供 PyInstaller 构建，并在结束时删除；临时源码和 EXE 都被 `.gitignore` 排除，不会误提交 token。

> 预配置 EXE 中的 token 仍可能被逆向提取。当前 Relay 是单一共享 token，只应在自用、受信任客户或每位客户独立 Relay 的场景使用，不能把同一个生产 token 发给互不信任的客户。

## 源码调试方式

开发时也可以使用 `agent.config.json` 直接运行 Python：

```powershell
Copy-Item agent.config.example.json agent.config.json
# 编辑 relay_ws 和 token 后：
python agent.py --run
```

配置也可通过命令行覆盖：`--relay`、`--token`、`--device-id`、`--name`、`--adb`、`--fastboot`。普通 `build.bat` 只生成未预配置的开发版 EXE，需要与 `agent.config.json` 配套；交付客户请使用 `build-customer.ps1`。

## 你这边怎么用

agent 上线后，`ard devices` 会多出一个 `host-xxx`（名字以 `PC-` 开头）：

```bash
# CLI
ard devices
ard host-which   <host-id>
ard host-adb      <host-id> devices
ard host-adb      <host-id> shell getprop ro.product.model
ard host-fastboot <host-id> devices
ard host-exec     <host-id> "adb reboot bootloader"
```

或在支持 MCP 的客户端中使用：`host_which` / `host_adb` / `host_fastboot` / `host_exec`。

典型救砖流程（手机黑砖/死机）：
```bash
ard host-adb      <host-id> reboot bootloader     # 重启进 fastboot
ard host-fastboot <host-id> devices               # 确认 fastboot 模式
ard host-fastboot <host-id> flash boot boot.img    # 刷分区
ard host-fastboot <host-id> reboot
```

> 刷机镜像需要先在客户电脑上（agent 用 `host.exec` 下载，或人工拷到电脑）。

## 卸载

右键 `uninstall-autostart.bat` → 以管理员身份运行。
或手动：`schtasks /Delete /TN ARD-Host-Agent /F`
