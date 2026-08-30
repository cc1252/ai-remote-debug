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
echo 把 dist\ard-host-agent.exe 和 agent.config.example.json 一起拷到客户电脑,
echo 重命名配置为 agent.config.json 放在 exe 同目录, 再运行 install-autostart.bat
endlocal
