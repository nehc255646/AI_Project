@echo off
setlocal
title AI 对话后端服务
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
start "" /min cmd /c "timeout /t 3 >nul & start http://localhost:8000"
python -m uvicorn main:app --host 0.0.0.0 --port 8000
echo.
echo 服务已停止，按任意键关闭窗口
pause >nul
endlocal
