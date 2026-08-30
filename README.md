# AI Remote Debug (ARD)

[简体中文](README.md) | [English](README.en.md)

[![CI](https://github.com/cc1252/ai-remote-debug/actions/workflows/ci.yml/badge.svg)](https://github.com/cc1252/ai-remote-debug/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**让 AI 在获得授权后进入客户的真实运行环境，直接查证问题，而不是隔着聊天窗口猜问题。**

**Give AI an authorized path into the customer's real environment—so it can diagnose facts instead of guessing through a chat window.**

AI 正在让软件制作越来越快，但软件交付到客户手上后，排障仍然很原始：客户说不清现象，开发者拿不到现场日志，AI 看不到真实环境，最后只能反复截图、远程桌面和人工猜测。

AI Remote Debug（ARD）就是为这个断点设计的。它在客户电脑或 Android 设备上运行一个主动连接的执行端，把日志、系统状态、命令结果、文件和调试能力通过自托管 Relay 提供给 CLI 与 MCP 客户端。AI 可以在工程师监督下收集证据、定位环境差异，并执行经过确认的修复操作。

ARD 不只是 Android 工具，而是一套面向 AI 时代的软件售后、远程诊断与现场问题处理基础设施。

## 它要解决的问题

```text
软件在开发机正常
        ↓
交付到客户环境后出问题
        ↓
客户不会描述 / 日志拿不到 / 环境无法复现
        ↓
AI 和工程师缺少真实上下文，只能来回沟通和猜测
```

ARD 把最后一段连接补上：**让 AI 能够触达经过授权的客户现场，并基于真实证据排查问题。**

## 为什么值得用

- **AI 原生，而不是把远程桌面交给 AI 点鼠标**：MCP 与 CLI 提供明确的工具和结构化结果，便于 AI 读取状态、调用诊断并持续推理。
- **远程电脑是一等执行端**：PC Host Agent 可以检查客户电脑的进程、服务、日志、文件、网络和运行环境，也能执行获得授权的修复命令。
- **Android 深度调试**：Android Executor 提供 logcat、应用管理、root shell、输入控制、截图、APK 安装和文件传输。
- **系统故障仍有第二条路**：Android 无法进入系统时，可通过旁边的 PC Host Agent 继续执行 ADB/fastboot，覆盖黑屏、recovery 和 fastboot 场景。
- **客户侧主动连接**：PC Agent 和 Android App 都主动连接 Relay，不要求客户拥有固定 IP，也不需要把客户电脑或 ADB 端口直接暴露到公网。
- **自托管，数据路径自己掌控**：Relay 是轻量 FastAPI 服务，不依赖第三方远控平台；支持 Python 或 Docker Compose 部署。
- **适合长期售后与持续维护**：支持心跳、断线重连、Android 前台服务和可选的 PC 开机自启，让一次交付后的问题也能持续被诊断。

## 典型场景

| 场景 | ARD 能解决什么 |
|---|---|
| 客户电脑上的软件报错 | 直接检查进程、服务、配置、文件、网络和运行日志，减少来回询问 |
| “开发环境正常，客户环境失败” | 让 AI 对比真实系统信息和依赖状态，定位环境差异 |
| AI 制作软件后的远程售后 | 让写代码的 AI 继续参与交付后的诊断和修复闭环 |
| 异地 Android 测试机 | 不到现场也能查日志、截屏、装包、重启应用和执行 shell |
| 远程技术支持 | 在明确授权下，通过客户电脑执行诊断，或控制其 USB 连接的 Android 设备 |
| 黑屏、recovery、fastboot | Android App 不在线时，仍可通过 PC Host Agent 继续救援 |

```powershell
# 查看所有在线客户电脑和 Android 节点
python claude-tools\ard.py devices

# 检查客户电脑的系统与 ADB/fastboot 环境
python claude-tools\ard.py host-which <customer-pc>

# 在明确确认后执行电脑诊断命令
python claude-tools\ard.py host-exec <customer-pc> "systeminfo" --confirm

# 拉取客户 Android 设备最近 200 行日志
python claude-tools\ard.py logcat <android-device> --lines 200

# Android 无法进入系统时，从旁边的电脑检查 fastboot
python claude-tools\ard.py host-fastboot <customer-pc> devices
```

> [!WARNING]
> ARD 能在已连接的客户电脑和 Android 设备上执行高权限命令。必须获得设备所有者的明确授权。持有 Relay token 的人可能取得设备控制权；公网部署必须使用 HTTPS/WSS、随机长 token 和访问控制。

项目目前处于早期阶段，协议和配置可能变化。Relay 使用单一共享 token，设备状态保存在内存中，适合个人团队、小规模售后或受信任网络，还不是具备租户隔离、细粒度权限和审计能力的企业远程支持平台。

## 工作方式

```text
        AI Agent / Engineer
                │
           CLI / MCP
                │ HTTPS
                ▼
          Self-hosted Relay
           ▲             ▲
       WSS │             │ WSS
           │             │
Customer PC Host Agent   Android Executor
apps / logs / shell      logcat / root / files
adb / fastboot / files   screenshot / install
```

| 组件 | 作用 | 运行位置 |
|---|---|---|
| `relay-server` | 设备注册、命令转发、日志流和临时文件中转 | 自托管服务器 |
| `pc-agent` | 诊断客户电脑，执行主机命令、ADB 和 fastboot | Windows 客户电脑（交付为单个 EXE） |
| `mobile-executor` | 执行 Android logcat、shell/root、应用和文件操作 | Android 8.0+ 设备 |
| `claude-tools` | 向工程师、脚本和 AI 提供 `ard` CLI 与 MCP Server | 操作者电脑或 AI 工具环境 |

PC Agent 不依赖 Android App：它既可以诊断客户电脑自身，也可以控制通过 USB 连接的 Android 设备。Android 端多数文件、应用和输入操作需要 root。

## 快速开始

### 客户实际怎么用

客户侧只有一步：**双击你发给他的 `ard-host-agent.exe`**。

首次运行时，程序会让客户填写一个便于技术支持识别的电脑名称，并弹出 Windows 管理员授权；确认后自动安装为开机自启服务并上线。客户电脑不需要安装 Python、不需要编辑配置文件，也不需要执行命令。以后再次双击同一个 EXE，可以重新启动服务或卸载。

Relay 地址和连接 token 由项目部署者在生成客户版 EXE 时预先写入。下面的步骤是给部署者和开发者看的，不是让客户操作的。

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

### 2. 生成发给客户的单文件 EXE

```powershell
cd pc-agent
python -m venv .build-venv
.\.build-venv\Scripts\pip install -r requirements.txt pyinstaller

# 使用与 Relay 相同的 token；脚本不会把它写入 Git 中的源码
$env:ARD_API_TOKEN = "<与 Relay 相同的 token>"
.\build-customer.ps1 -RelayWs "wss://relay.example.com/ws/mobile"
Remove-Item Env:\ARD_API_TOKEN
```

构建产物是 `pc-agent\release\ard-host-agent.exe`。只把这一个文件发给客户，客户双击即可完成命名、授权、安装和上线。详细说明见 [PC Agent 说明](pc-agent/README.md)。

> PC Agent 能执行任意主机命令。安装前必须获得电脑所有者授权，并明确告知其权限范围和停止、卸载方式。

> [!IMPORTANT]
> 预配置 EXE 中的 token 可以被有能力的用户提取。当前 Relay 仍是单一共享 token，因此此方式只适合自用、受信任客户或每位客户独立部署的 Relay；不要把同一个生产 token 打包后分发给互不信任的客户。

### 3. 可选：连接 Android 执行端

如果交付的软件运行在 Android 上，或需要同时诊断客户电脑连接的 Android 设备，可以安装 Android Executor。构建需要 JDK 17、Android SDK 34 和 Gradle 8.2.1：

```powershell
cd mobile-executor
gradle :app:assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

打开 App，填写设备名称、Relay WebSocket 地址和相同的 token，然后点击“一键启动远程调试”。App 只会在用户手动启用后设置开机自启，并始终显示前台服务通知。

### 4. 从工程师或 AI 侧使用 CLI

在操作者电脑配置 Relay：

```powershell
$env:ARD_RELAY_URL = "http://127.0.0.1:8000"
$env:ARD_API_TOKEN = "<与 Relay 相同的 token>"

# 发现客户电脑和 Android 设备
python claude-tools\ard.py devices

# 诊断客户电脑
python claude-tools\ard.py host-which <customer-pc>
python claude-tools\ard.py host-exec <customer-pc> "systeminfo" --confirm

# 诊断 Android
python claude-tools\ard.py device <android-device> info
python claude-tools\ard.py logcat <android-device> --lines 200
```

更多 PC 与 Android 操作：

```powershell
python claude-tools\ard.py host-which <host-id>
python claude-tools\ard.py host-adb <host-id> devices
python claude-tools\ard.py host-fastboot <host-id> devices
python claude-tools\ard.py host-exec <host-id> "whoami" --confirm
python claude-tools\ard.py shell <android-device> "id" --confirm
python claude-tools\ard.py push <android-device> .\local.apk /data/local/tmp/local.apk --confirm
```

运行 `python claude-tools\ard.py --help` 查看全部命令。

## MCP 接入

MCP 是 ARD 面向 AI 的核心入口。客户明确授权并部署执行端后，AI 不只是给出排障建议，还可以发现客户节点、读取真实状态并调用远程诊断能力。是否对每次工具调用再次确认，取决于所使用的 MCP 客户端权限设置。

`claude-tools/ard_mcp.py` 提供 stdio MCP Server。安装依赖后，在支持 MCP 的客户端中把启动命令配置为该 Python 文件，并设置 `ARD_RELAY_URL`、`ARD_API_TOKEN` 两个环境变量：

```powershell
python -m pip install -r claude-tools\requirements.txt
python claude-tools\ard_mcp.py
```

不要把 token 直接写入会提交到仓库的 MCP 配置。不同客户端的配置格式不同，请参考对应客户端的 MCP Server 文档。

## AI Skill

仓库同时提供可直接交给 AI 使用的 [`ai-remote-debug` Skill](skills/ai-remote-debug/SKILL.md)。它让 AI 不只是知道有哪些命令，还会按远程排障流程工作：先发现并确认设备，再收集最小必要证据、形成诊断假设，获得授权后才执行修改，并在最后验证结果。

将整个 `skills/ai-remote-debug` 文件夹复制到支持 `SKILL.md` 的 AI 客户端技能目录，或让客户端直接加载该目录。配置好上面的 ARD MCP Server 后，可以这样发起任务：

```text
使用 $ai-remote-debug 排查“客户A-收银台电脑”上的程序为什么无法启动，先只收集证据，不要修改客户环境。
```

Skill 同时支持 MCP 和 `ard` CLI 回退，并内置了客户授权、敏感数据最小化、命令确认、ADB/fastboot 高风险操作等边界。

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

这部分是源码调试方式。正式交付给客户时，使用 `build-customer.ps1` 将 Relay 地址和 token 预置进单文件 EXE，客户无需接触这些配置。

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
