@echo off
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
start /b python -m uvicorn main:app --host 0.0.0.0 --port 8000

timeout /t 2 >nul 2>&1
start http://localhost:8000

echo ========================================
echo   Visit http://localhost:8000
echo ========================================
pause >nul

:: Cleanup
taskkill /f /im python.exe >nul 2>&1
