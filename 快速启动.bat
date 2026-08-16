@echo off
setlocal
chcp 65001 >nul
title AI Chat Agent
cd /d "%~dp0"

echo [1/3] 检查 Python...
set "PY=python"
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
"%PY%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到可用的 Python，请先运行“重置启动.bat”安装依赖。
    pause
    exit /b 1
)
echo [1/3] Python 可用

echo [2/3] 检查 8000 端口...
"%SystemRoot%\System32\netstat.exe" -ano | "%SystemRoot%\System32\findstr.exe" "LISTENING" | "%SystemRoot%\System32\findstr.exe" ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo [提示] 8000 端口已有服务，直接打开现有服务。
    start http://localhost:8000
    echo.
    pause
    exit /b 0
)
echo [2/3] 端口可用

echo [3/3] 启动后端服务
cd /d "%~dp0backend"
start "" /min cmd /c "%SystemRoot%\System32\timeout.exe /t 3 >nul & start http://localhost:8000"
"%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level info
echo.
echo 服务停止后请关闭此窗口。
pause >nul
endlocal
