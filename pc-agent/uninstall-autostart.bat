@echo off
REM 卸载 PC Host Agent 自启动并停止运行。右键"以管理员身份运行"。
setlocal
set TASK=ARD-Host-Agent

echo 停止并删除计划任务: %TASK%
schtasks /End /TN "%TASK%" >nul 2>&1
schtasks /Delete /TN "%TASK%" /F

echo 结束残留进程...
taskkill /IM ard-host-agent.exe /F >nul 2>&1

echo 完成。
pause
endlocal
