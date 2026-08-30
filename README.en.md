# AI Remote Debug (ARD)

[简体中文](README.md) | [English](README.en.md)

[![CI](https://github.com/cc1252/ai-remote-debug/actions/workflows/ci.yml/badge.svg)](https://github.com/cc1252/ai-remote-debug/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Give AI an authorized path into the customer's real environment—so it can diagnose facts instead of guessing through a chat window.**

AI is making software dramatically faster to build, but post-delivery troubleshooting is still painfully manual. A customer cannot describe the failure precisely, developers cannot access on-site logs, the environment cannot be reproduced, and the AI that wrote the software has no visibility into where it actually runs.

AI Remote Debug (ARD) closes that gap. A lightweight agent on a customer PC or Android device connects outbound to a self-hosted Relay. Engineers, scripts, and MCP-compatible AI clients can then inspect real system state, collect evidence, run diagnostics, transfer files, and—when explicitly authorized—perform remediation.

ARD is not merely an Android utility. It is open-source infrastructure for AI-era software support, remote diagnostics, and post-delivery problem resolution.

## The problem ARD solves

```text
Software works on the developer's machine
                 ↓
It fails in the customer's environment
                 ↓
No useful logs / unclear symptoms / environment cannot be reproduced
                 ↓
The engineer and AI lack real context and are forced to guess
```

ARD provides the missing last mile: **an authorized, tool-oriented connection between AI and the customer's real runtime environment.**

## Why ARD

- **AI-native diagnostics**: MCP and CLI expose explicit tools and machine-readable results instead of asking an AI to click through a remote desktop.
- **Customer PCs are first-class targets**: the PC Host Agent can inspect processes, services, logs, files, network state, and runtime dependencies, then execute authorized remediation commands.
- **Deep Android debugging**: the Android Executor supports logcat, app management, root shell, input control, screenshots, APK installation, and file transfer.
- **A second path when Android cannot boot**: the PC Agent can continue through USB with ADB or fastboot in black-screen, recovery, and fastboot scenarios.
- **Outbound customer-side connections**: agents do not require a static customer IP and do not expose the customer's PC or ADB port directly to the public internet.
- **Self-hosted data path**: the Relay is a lightweight FastAPI service that can run with Python or Docker Compose.
- **Built for ongoing support**: heartbeat, reconnection, Android foreground service, and optional PC autostart support long-lived deployments.

## Typical use cases

| Use case | What ARD provides |
|---|---|
| Software fails on a customer PC | Inspect processes, services, configuration, files, network state, and logs without repeated back-and-forth |
| “Works here, fails there” | Let AI compare the real system and dependency state to identify environmental differences |
| Support for AI-built software | Keep the AI involved after delivery, from diagnosis through an authorized remediation workflow |
| Remote Android test devices | Read logs, capture screens, install builds, restart apps, and run shell commands without visiting the device |
| Remote technical support | Diagnose a customer PC or control an authorized Android device connected to that PC over USB |
| Black screen, recovery, or fastboot | Continue troubleshooting through the PC Host Agent when the Android app is offline |

```powershell
# Discover connected customer PCs and Android devices
python claude-tools\ard.py devices

# Inspect a customer PC and its ADB/fastboot environment
python claude-tools\ard.py host-which <customer-pc>

# Run a host diagnostic after explicit confirmation
python claude-tools\ard.py host-exec <customer-pc> "systeminfo" --confirm

# Read recent logs from a remote Android device
python claude-tools\ard.py logcat <android-device> --lines 200

# Check fastboot through a nearby customer PC
python claude-tools\ard.py host-fastboot <customer-pc> devices
```

> [!WARNING]
> ARD can execute privileged commands on connected customer PCs and Android devices. Use it only with the device owner's explicit authorization. Anyone holding the Relay token may gain control of connected nodes. Internet-facing deployments must use HTTPS/WSS, a long random token, and additional access controls.

ARD is currently an early-stage project. The Relay uses one shared token and keeps device state in memory. It is suitable for individuals, small support teams, labs, and trusted networks; it is not yet an enterprise remote-support platform with tenant isolation, fine-grained authorization, and audit logging.

## Architecture

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

| Component | Responsibility | Runs on |
|---|---|---|
| `relay-server` | Device registration, command relay, log streaming, and temporary artifact transfer | A self-hosted server |
| `pc-agent` | Customer PC diagnostics, host commands, ADB, and fastboot | A Windows customer PC (delivered as one EXE) |
| `mobile-executor` | Android logcat, shell/root, app, input, screenshot, and file operations | Android 8.0+ |
| `claude-tools` | The `ard` CLI and MCP Server for engineers, scripts, and AI clients | The operator or AI environment |

The PC Agent does not depend on the Android app. It can diagnose the customer PC itself or control an Android device connected over USB. Most privileged Android file, app, and input operations require root.

## Quick start

### What the customer actually does

The customer has one step: **double-click the `ard-host-agent.exe` you send them**.

On first launch, the agent asks for a recognizable computer name and requests Windows administrator approval. It then installs itself for automatic startup and comes online. The customer does not install Python, edit configuration files, or run commands. Double-clicking the same EXE later provides restart and uninstall options.

The project operator embeds the Relay address and connection token while creating the customer EXE. The remaining steps are for operators and developers, not customers.

### 1. Start the Relay

Generate a random token and start the Python service:

```powershell
$env:ARD_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
python -m venv .venv
.\.venv\Scripts\pip install -r relay-server\requirements.txt
.\.venv\Scripts\uvicorn --app-dir relay-server main:app --host 127.0.0.1 --port 8000
```

Or use Docker Compose:

```powershell
docker compose up --build
```

The Relay rejects missing, placeholder, or shorter-than-32-character tokens. For remote access, deploy it behind HTTPS/WSS and appropriate network controls.

### 2. Build the single-file customer EXE

```powershell
cd pc-agent
python -m venv .build-venv
.\.build-venv\Scripts\pip install -r requirements.txt pyinstaller

# Use the same token as the Relay. The script does not write it to tracked source.
$env:ARD_API_TOKEN = "<the same Relay token>"
.\build-customer.ps1 -RelayWs "wss://relay.example.com/ws/mobile"
Remove-Item Env:\ARD_API_TOKEN
```

The output is `pc-agent\release\ard-host-agent.exe`. Send only this file to the customer; double-clicking it handles naming, authorization, installation, and connection. See the [PC Agent guide](pc-agent/README.md) for details.

> [!IMPORTANT]
> A capable user can extract a token embedded in an EXE. The current Relay uses one shared token, so this delivery mode is appropriate only for personal use, trusted customers, or a dedicated Relay per customer. Do not distribute one production token among mutually untrusted customers.

### 3. Optionally connect Android

Building the Android Executor requires JDK 17, Android SDK 34, and Gradle 8.2.1:

```powershell
cd mobile-executor
gradle :app:assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Open the app, enter a device name, the Relay WebSocket URL, and the same token, then start remote debugging. The app only enables autostart after the user explicitly starts it and always displays a foreground-service notification.

### 4. Use the CLI

```powershell
$env:ARD_RELAY_URL = "http://127.0.0.1:8000"
$env:ARD_API_TOKEN = "<the same Relay token>"

python claude-tools\ard.py devices
python claude-tools\ard.py host-which <customer-pc>
python claude-tools\ard.py host-exec <customer-pc> "systeminfo" --confirm
python claude-tools\ard.py device <android-device> info
python claude-tools\ard.py logcat <android-device> --lines 200
```

Run `python claude-tools\ard.py --help` for the full command list.

## MCP integration

MCP is ARD's primary AI interface. Once the device owner has authorized and deployed an executor, an AI client can discover customer nodes, inspect real state, and invoke diagnostic tools. Per-tool confirmation depends on the permission settings of the MCP client in use.

```powershell
python -m pip install -r claude-tools\requirements.txt
python claude-tools\ard_mcp.py
```

Configure the stdio MCP Server with `ARD_RELAY_URL` and `ARD_API_TOKEN`. Do not commit the token to a client configuration stored in source control.

## Security model

- Terminate HTTPS/WSS at a maintained reverse proxy or gateway for internet deployments.
- Use a random `ARD_API_TOKEN` of at least 32 characters and rotate it when access changes.
- Restrict Relay access with a firewall, VPN, or identity-aware proxy.
- Treat the PC Agent as arbitrary command execution; disclose its permissions and uninstall path to the device owner.
- Remove sensitive artifacts after transfer and protect `ARD_ARTIFACT_DIR` at rest.
- See [SECURITY.md](SECURITY.md) for deployment guidance and private vulnerability reporting.

## Development

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r relay-server\requirements.txt -r requirements-dev.txt
$env:ARD_API_TOKEN = "test-token-that-is-longer-than-thirty-two-characters"
.\.venv\Scripts\pytest -q
.\.venv\Scripts\python -m compileall -q relay-server pc-agent claude-tools tests
```

Pull requests run tests on Python 3.10 and 3.13 and build the Android debug APK. See [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

## License

AI Remote Debug is available under the [MIT License](LICENSE).
