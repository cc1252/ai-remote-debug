@echo off
REM 打包 PC Host Agent 成单文件 exe。开发机上运行一次即可。
REM 产物: dist\ard-host-agent.exe

setlocal
cd /d "%~dp0"

set PY="C:\Program Files\Python313\python.exe"
if not exist %PY% set PY=python

echo [1/2] 清理旧产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] PyInstaller 打包...
%PY% -m PyInstaller ^
  --onefile ^
  --name ard-host-agent ^
  --console ^
  --hidden-import websockets ^
  agent.py

if errorlevel 1 (
  echo.
  echo 打包失败。请确认已安装 pyinstaller 和 websockets:
  echo   %PY% -m pip install pyinstaller -r requirements.txt
  exit /b 1
)

echo.
echo 完成: dist\ard-host-agent.exe
echo 这是未预配置的开发版, 需要在 EXE 同目录放置 agent.config.json。
echo 要生成客户双击即可安装的单文件版, 请使用 build-customer.ps1。
endlocal
