@echo off
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

:: Launch python 
start /b python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

start http://localhost:8000

echo ========================================
echo   Server started!
echo   Visit http://localhost:8000

pause

