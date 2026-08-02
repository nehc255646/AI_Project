@echo off
setlocal
title AI 对话机器人服务
cd /d "%~dp0"

rem 优先使用后端虚拟环境中的 Python
set "PY=python"
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"

"%PY%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 或运行「重置启动.bat」初始化环境。
    pause
    exit /b 1
)
echo [1/2] Python 就绪

rem 检查 8000 端口是否已被占用（服务可能已在运行）
netstat -ano | findstr "LISTENING" | findstr ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo [提示] 端口 8000 已有服务在运行，直接打开浏览器访问。
    start http://localhost:8000
    echo.
    pause
    exit /b 0
)

echo [2/2] 启动后端服务，每次请求的日志将实时显示在本窗口...
cd /d "%~dp0backend"
start "" /min cmd /c "timeout /t 3 >nul & start http://localhost:8000"
"%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info

echo.
echo 服务已停止，按任意键关闭窗口
pause >nul
endlocal
