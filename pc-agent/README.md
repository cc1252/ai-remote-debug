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

## 部署到客户电脑

### 方式 A：打包 exe（客户电脑没装 Python，推荐）

1. 开发机上先装依赖并打包：
   ```bat
   "C:\Program Files\Python313\python.exe" -m pip install pyinstaller -r requirements.txt
   build.bat
   ```
   产物在 `dist\ard-host-agent.exe`。

2. 把这三个文件拷到客户电脑同一目录（如 `C:\ard-agent\`）：
   - `dist\ard-host-agent.exe`
   - `agent.config.example.json` → 重命名为 `agent.config.json`
   - `install-autostart.bat`

3. 编辑 `agent.config.json`：填好 `relay_ws` 和至少 32 个字符的随机 `token`。示例文件只包含本地地址和无效占位值，不能直接用于部署。
   `name` 留空会用机器名，`device_id` 留空会按机器名生成稳定 id。

4. 右键 `install-autostart.bat` → **以管理员身份运行**。
   它会建一个开机自启的计划任务（SYSTEM 权限，开机即跑，无需登录），并立即启动。

### 方式 B：直接跑 Python（客户电脑有 Python）

```bat
"C:\Program Files\Python313\python.exe" agent.py --name "客户A电脑"
```
配置也可通过命令行覆盖：`--relay`、`--token`、`--device-id`、`--adb`、`--fastboot`。

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
