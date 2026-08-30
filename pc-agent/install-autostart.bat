@echo off
REM 在客户电脑上安装 PC Host Agent 自启动 (开机自动后台运行)。
REM 用法: 把 ard-host-agent.exe + agent.config.json + 本脚本放同一目录, 右键"以管理员身份运行"。

setlocal
cd /d "%~dp0"

set EXE=%~dp0ard-host-agent.exe
set TASK=ARD-Host-Agent

if not exist "%EXE%" (
  echo 找不到 %EXE%
  echo 请先把 ard-host-agent.exe 放到本脚本同目录。
  pause
  exit /b 1
)

echo 创建开机自启计划任务: %TASK%
REM /RL HIGHEST 拿到管理员权限 (adb/fastboot 需要); /RU SYSTEM 开机即跑不需要登录
schtasks /Create /TN "%TASK%" /TR "\"%EXE%\"" /SC ONSTART /RU SYSTEM /RL HIGHEST /F
if errorlevel 1 (
  echo 创建计划任务失败 (需要管理员权限)。
  pause
  exit /b 1
)

echo 立即启动一次...
schtasks /Run /TN "%TASK%"

echo.
echo 安装完成。Agent 已设为开机自启, 并已启动。
echo 卸载: schtasks /Delete /TN "%TASK%" /F
echo 查看状态: schtasks /Query /TN "%TASK%"
pause
endlocal
