# 参与贡献

感谢你愿意改进 AI Remote Debug。这个项目能够在远程电脑或 Android 设备上执行高权限命令，因此功能改动和安全边界同样重要。

## 开始之前

- 功能建议和普通缺陷请先提交 Issue，说明使用场景、预期行为和复现方式。
- 安全漏洞不要提交公开 Issue，请按 [SECURITY.md](SECURITY.md) 私下报告。
- 只在你拥有或已获明确授权的设备上测试。

## 本地开发

需要 Python 3.10+、JDK 17 和 Android SDK 34。各组件可以独立运行。

```powershell
# Relay 与测试
python -m venv .venv
.\.venv\Scripts\pip install -r relay-server\requirements.txt -r requirements-dev.txt
$env:ARD_API_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
.\.venv\Scripts\pytest

# Python 语法检查
.\.venv\Scripts\python -m compileall -q relay-server pc-agent claude-tools

# Android（已安装 Gradle 时）
cd mobile-executor
gradle :app:assembleDebug
```

PC Agent 的运行依赖见 `pc-agent/requirements.txt`，MCP 适配器的依赖见 `claude-tools/requirements.txt`。

## 提交 Pull Request

1. 从 `main` 创建小而聚焦的分支。
2. 不要提交 token、设备标识、日志、客户信息、APK 或构建产物。
3. 新功能应补充测试或说明无法自动测试的原因。
4. 行为、配置或安全边界变化时同步更新 README。
5. 确认 CI 通过，并在 PR 中列出测试方式和潜在风险。

提交信息建议使用简洁的祈使句；项目现有历史采用 `feat:`、`fix:` 等 Conventional Commits 前缀，但不强制。
