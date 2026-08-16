@echo off
setlocal
title AI Chat Agent
cd /d "%~dp0"

echo [1/3] Python 检查中...
set "PY=python"
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
"%PY%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到可用的 Python，请安装 Python 或运行「重置启动.bat」。
    pause
    exit /b 1
)
echo [1/3] Python 就绪

echo [2/3] 检查 8000 端口...
"%SystemRoot%\System32\netstat.exe" -ano | "%SystemRoot%\System32\findstr.exe" "LISTENING" | "%SystemRoot%\System32\findstr.exe" ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo [提示] 端口 8000 已有服务在运行，直接打开浏览器访问。
    start http://localhost:8000
    echo.
    pause
    exit /b 0
)
echo [2/3] 端口空闲

echo [3/3] 启动后端服务
cd /d "%~dp0backend"
start "" /min cmd /c "%SystemRoot%\System32\timeout.exe /t 3 >nul & start http://localhost:8000"
"%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info
echo.
echo 服务已停止，按任意键关闭窗口
pause >nul
endlocal
