@echo off
setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)
echo [1/2] Python OK

echo [2/2] Starting backend server...
cd /d "%~dp0backend"

:: 启动后端并记录 PID（退出时只结束自己启动的进程，不再误杀系统其他 Python 进程）
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$p = Start-Process python -ArgumentList '-m','uvicorn','main:app','--host','0.0.0.0','--port','8000' -WorkingDirectory '%~dp0backend' -WindowStyle Hidden -PassThru; $p.Id"`) do set SERVER_PID=%%p

timeout /t 2 >nul 2>&1
start http://localhost:8000

echo ========================================
echo   Visit http://localhost:8000
echo ========================================
pause >nul

:: 只结束自己启动的后端进程（/t 连带终止其子进程）
if defined SERVER_PID taskkill /f /t /pid %SERVER_PID% >nul 2>&1
endlocal
