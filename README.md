# Android Remote Debug

[![CI](https://github.com/cc1252/android-remote-debug-oss/actions/workflows/ci.yml/badge.svg)](https://github.com/cc1252/android-remote-debug-oss/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**让 Android 调试摆脱 USB 线、局域网和远程桌面。**

Android Remote Debug（ARD）把分散在不同网络、不同地点的 Android 设备，变成可以通过命令行和 MCP 直接操作的远程调试节点。设备主动连接你自己的 Relay，无需暴露 ADB 端口；需要救援时，还可以通过设备旁边的 PC Agent 执行 ADB 和 fastboot。

一句话概括：**把 `adb`、root shell、日志、截图、文件传输和救砖能力，安全地搬到任何能访问 Relay 的地方。**

## 为什么值得用

- **设备主动上线，不需要公网 ADB**：Android App 和 PC Agent 都通过 WebSocket 主动连接 Relay，适合 NAT、动态 IP 和跨网络环境。
- **正常调试与故障救援双通道**：系统正常时使用 Android Executor；无法进入系统时，通过旁边的 PC Agent 继续执行 ADB/fastboot。
- **为自动化和 AI 工具而生**：同时提供 CLI 与 MCP Server，可接入脚本、CI、IDE 和支持 MCP 的 AI 编程助手。
- **自托管，数据路径自己掌控**：Relay 是轻量 FastAPI 服务，不依赖第三方远控平台；支持 Python 或 Docker Compose 部署。
- **不仅是远程 shell**：内置 logcat、应用管理、输入控制、截图、APK 安装、分块文件传输和 Artifact 中转。
- **适合长期在线设备**：支持心跳、断线重连、Android 前台服务和可选的 PC 开机自启。

## 典型场景

| 场景 | ARD 能解决什么 |
|---|---|
| 异地测试机 | 不到现场也能查日志、截屏、装包、重启应用和执行 shell |
| Android 实验室 | 用统一 CLI 管理多台 root 设备，便于脚本化批量排查 |
| 远程技术支持 | 在明确授权下，通过客户电脑的 USB 连接执行 ADB/fastboot |
| 黑屏、recovery、fastboot | Android App 不在线时，仍可通过 PC Host Agent 继续救援 |
| AI 辅助调试 | 让 MCP 客户端直接读取设备状态、日志和命令结果 |

```powershell
# 查看所有在线 Android / PC 节点
python claude-tools\ard.py devices

# 拉取远程设备最近 200 行日志
python claude-tools\ard.py logcat <device> --lines 200

# 远程执行 root shell（危险操作需要显式确认）
python claude-tools\ard.py shell <device> "dumpsys battery" --confirm

# 手机无法进系统时，从旁边的 PC 检查 fastboot
python claude-tools\ard.py host-fastboot <host> devices
```

> [!WARNING]
> ARD 能在已连接设备上执行高权限命令。仅用于你拥有或已获明确授权的设备。持有 Relay token 的人可能取得设备控制权；公网部署必须使用 HTTPS/WSS、随机长 token 和访问控制。

项目目前处于早期阶段，协议和配置可能变化。Relay 使用单一共享 token，设备状态保存在内存中，适合个人、实验室或小型受信任网络，不是多租户设备管理平台。

## 工作方式

```text
CLI / MCP ── HTTPS ──┐
                     ▼
                  Relay
                 ▲     ▲
          WSS ───┘     └─── WSS
   Android Executor       PC Host Agent
   root / shell / files   adb / fastboot / shell
```

| 组件 | 作用 | 运行位置 |
|---|---|---|
| `relay-server` | 设备注册、命令转发、日志流和临时文件中转 | 自托管服务器 |
| `mobile-executor` | 执行 Android shell/root 命令并回传结果 | Android 8.0+ 设备 |
| `pc-agent` | 执行 ADB、fastboot 或主机命令 | 连接手机的 PC |
| `claude-tools` | `ard` CLI 和 MCP Server | 操作者电脑 |

Android 端多数文件、应用和输入操作需要 root；PC Agent 不依赖 Android App，可在设备无法进入系统时通过 USB 执行 ADB/fastboot。

## 快速开始

### 1. 启动 Relay

先生成随机 token。下面的命令会把 token 留在当前终端环境中，不会写入仓库。

```powershell
$env:ARD_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
```

使用 Python 启动：

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r relay-server\requirements.txt
.\.venv\Scripts\uvicorn --app-dir relay-server main:app --host 127.0.0.1 --port 8000
```

也可以使用 Docker Compose：

```powershell
docker compose up --build
```

访问 `http://127.0.0.1:8000/health`，返回 `{"status":"ok"}` 即表示 Relay 可用。Relay 会拒绝缺失、占位或短于 32 个字符的 token。

### 2. 连接 Android 执行端

构建需要 JDK 17、Android SDK 34 和 Gradle 8.2.1：

```powershell
cd mobile-executor
gradle :app:assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

打开 App，填写：

- 设备显示名称；
- Relay WebSocket 地址，例如 `ws://192.168.1.10:8000/ws/mobile`；
- 与 Relay 相同的 token。

点击“一键启动远程调试”。App 只会在用户手动启用后设置开机自启，并始终显示前台服务通知。局域网开发可以使用 `ws://`；生产部署必须使用 `wss://`。

### 3. 使用 CLI

在操作者电脑配置 Relay：

```powershell
$env:ARD_RELAY_URL = "http://127.0.0.1:8000"
$env:ARD_API_TOKEN = "<与 Relay 相同的 token>"
python claude-tools\ard.py devices
python claude-tools\ard.py device <device-id-or-name> info
python claude-tools\ard.py logcat <device-id-or-name> --lines 200
```

会修改设备状态的操作要求显式确认：

```powershell
python claude-tools\ard.py shell <device> "id" --confirm
python claude-tools\ard.py push <device> .\local.apk /data/local/tmp/local.apk --confirm
python claude-tools\ard.py adb-tcp <device> enable --confirm
```

运行 `python claude-tools\ard.py --help` 查看全部命令。

### 4. 可选：连接 PC Host Agent

```powershell
cd pc-agent
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
Copy-Item agent.config.example.json agent.config.json
# 编辑 agent.config.json 后：
.\.venv\Scripts\python agent.py --run
```

确认运行正常后，可以执行 `agent.py --install` 创建 Windows SYSTEM 开机任务。该模式等同于向 Relay token 持有者开放主机命令执行权限，请先阅读 [PC Agent 说明](pc-agent/README.md)。

```powershell
python claude-tools\ard.py host-which <host-id>
python claude-tools\ard.py host-adb <host-id> devices
python claude-tools\ard.py host-fastboot <host-id> devices
python claude-tools\ard.py host-exec <host-id> "whoami" --confirm
```

## MCP 接入

`claude-tools/ard_mcp.py` 提供 stdio MCP Server。安装依赖后，在支持 MCP 的客户端中把启动命令配置为该 Python 文件，并设置 `ARD_RELAY_URL`、`ARD_API_TOKEN` 两个环境变量：

```powershell
python -m pip install -r claude-tools\requirements.txt
python claude-tools\ard_mcp.py
```

不要把 token 直接写入会提交到仓库的 MCP 配置。不同客户端的配置格式不同，请参考对应客户端的 MCP Server 文档。

## 配置

### Relay 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|---|---:|---|---|
| `ARD_API_TOKEN` | 是 | 无 | 至少 32 个字符的随机共享 token |
| `ARD_ARTIFACT_DIR` | 否 | `artifacts` | 临时中转文件目录 |
| `ARD_MAX_ARTIFACT_BYTES` | 否 | `536870912` | 单个 Artifact 上限，默认 512 MiB |

### CLI / MCP 环境变量

| 变量 | 默认值 | 说明 |
|---|---|---|
| `ARD_RELAY_URL` | `http://127.0.0.1:8000` | Relay HTTP(S) 根地址 |
| `ARD_API_TOKEN` | 无 | Relay token |

### PC Agent 配置优先级

命令行参数 > 环境变量 > `agent.config.json` > 内置本地地址。将 [`agent.config.example.json`](pc-agent/agent.config.example.json) 复制为 `agent.config.json` 后使用；真实配置已被 `.gitignore` 排除。

## 生产部署与安全边界

- Relay 自身默认监听方式不提供 TLS。公网使用时，在反向代理或受控网关上终止 HTTPS/WSS，并限制来源网络。
- Artifact 下载使用 Authorization header，避免 token 出现在 URL 和常规访问日志中；中转文件仍是明文落盘，应设置目录权限并及时删除。
- Android App 会在本地偏好设置中保存连接信息，以支持用户选择的开机自启。root 设备上的本地恶意软件可能读取这些信息。
- 项目当前没有用户隔离、设备级 token、命令策略、审计日志或持久化设备状态。
- 不要把 Relay 暴露到不可信网络，不要使用生产主机测试 PC Agent 的任意命令能力。

详细部署基线和漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## 开发

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r relay-server\requirements.txt -r requirements-dev.txt
$env:ARD_API_TOKEN = "test-token-that-is-longer-than-thirty-two-characters"
.\.venv\Scripts\pytest -q
.\.venv\Scripts\python -m compileall -q relay-server pc-agent claude-tools tests
```

Pull Request 会自动在 Python 3.10/3.13 上运行测试，并构建 Android debug APK。参与开发前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目使用 [MIT License](LICENSE)。
