@echo off
setlocal
cd /d "%~dp0"

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found.
    pause
    exit /b 1
)
echo [1/4] Python OK

:: 2. Backend deps
echo [2/4] Installing backend dependencies...
python -m pip install -q -r backend\requirements.txt

:: 3. Frontend build
echo [3/4] Checking frontend...
node --version >nul 2>&1
if %errorlevel% equ 0 (
    echo    Building frontend...
    cd frontend
    if not exist "node_modules" call npm install --no-audit --no-fund
    call npm run build
    cd /d "%~dp0"
    echo [3/4] Frontend build done
) else (
    echo [3/4] Node.js not found, skip frontend build
)

:: 4. Start server 
echo [4/4] Starting server...
cd /d "%~dp0backend"

:: 启动后端并记录 PID（退出时只结束自己启动的进程）
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$p = Start-Process python -ArgumentList '-m','uvicorn','main:app','--host','0.0.0.0','--port','8000','--reload' -WorkingDirectory '%~dp0backend' -WindowStyle Hidden -PassThru; $p.Id"`) do set SERVER_PID=%%p

start http://localhost:8000

echo ========================================
echo   Server started!
echo   Visit http://localhost:8000

pause

:: 只结束自己启动的后端进程（/t 连带终止 reload 子进程）
if defined SERVER_PID taskkill /f /t /pid %SERVER_PID% >nul 2>&1
endlocal

