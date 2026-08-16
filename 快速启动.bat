@echo off
setlocal
chcp 65001 >nul
title AI Chat Agent
cd /d "%~dp0"

echo [1/3] Checking Python...
set "PY=python"
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
"%PY%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python was not found. Run the reset script first.
    pause
    exit /b 1
)
echo [1/3] Python is ready

echo [2/3] Checking port 8000...
"%SystemRoot%\System32\netstat.exe" -ano | "%SystemRoot%\System32\findstr.exe" "LISTENING" | "%SystemRoot%\System32\findstr.exe" ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Port 8000 is already in use. Opening the existing service.
    start http://localhost:8000
    echo.
    pause
    exit /b 0
)
echo [2/3] Port is available

echo [3/3] Starting backend service
cd /d "%~dp0backend"
start "" /min cmd /c "%SystemRoot%\System32\timeout.exe /t 3 >nul & start http://localhost:8000"
"%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level info
echo.
echo Close this window after the service stops.
pause >nul
endlocal
