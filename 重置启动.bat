@echo off
setlocal
chcp 65001 >nul
set "PY=python"
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
cd /d "%~dp0"

:: 1. 检查 Python
"%PY%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到可用的 Python。
    pause
    exit /b 1
)
echo [1/4] Python 可用

:: 2. 安装后端依赖
echo [2/4] 安装后端依赖...
"%PY%" -m pip install -q -r backend\requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 后端依赖安装失败。
    pause
    exit /b 1
)

:: 3. 构建前端
echo [3/4] 检查前端...
node --version >nul 2>&1
if %errorlevel% equ 0 (
    echo    正在构建前端...
    cd frontend
    if not exist "node_modules" call npm install --no-audit --no-fund
    call npm run build
    if errorlevel 1 (
        echo [错误] 前端构建失败。
        cd /d "%~dp0"
        pause
        exit /b 1
    )
    cd /d "%~dp0"
    echo [3/4] 前端构建完成
) else (
    echo [3/4] 未找到 Node.js，跳过前端构建
)

:: 4. 启动服务
echo [4/4] 启动服务...
cd /d "%~dp0backend"

:: 后台启动服务并记录 PID，退出时只结束服务进程树。
for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$p = Start-Process -FilePath '%PY%' -ArgumentList '-m','uvicorn','main:app','--host','127.0.0.1','--port','8000','--reload' -WorkingDirectory '%~dp0backend' -WindowStyle Hidden -PassThru; $p.Id"`) do set SERVER_PID=%%p

start http://localhost:8000

echo ========================================
echo   服务已启动！
echo   访问 http://localhost:8000

pause

:: 只结束当前启动的服务进程，/t 会同时结束 reload 子进程。
if defined SERVER_PID taskkill /f /t /pid %SERVER_PID% >nul 2>&1
endlocal

