@echo off
setlocal
title AI Chat Agent
cd /d "%~dp0"

echo [1/3] Python �����...
set "PY=python"
if exist "%~dp0backend\.venv\Scripts\python.exe" set "PY=%~dp0backend\.venv\Scripts\python.exe"
"%PY%" --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [����] δ�ҵ����õ� Python���밲װ Python �����С���������.bat����
    pause
    exit /b 1
)
echo [1/3] Python ����

echo [2/3] ��� 8000 �˿�...
"%SystemRoot%\System32\netstat.exe" -ano | "%SystemRoot%\System32\findstr.exe" "LISTENING" | "%SystemRoot%\System32\findstr.exe" ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo [��ʾ] �˿� 8000 ���з��������У�ֱ�Ӵ���������ʡ�
    start http://localhost:8000
    echo.
    pause
    exit /b 0
)
echo [2/3] �˿ڿ���

echo [3/3] ������˷���
cd /d "%~dp0backend"
start "" /min cmd /c "%SystemRoot%\System32\timeout.exe /t 3 >nul & start http://localhost:8000"
"%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level info
echo.
echo ������ֹͣ����������رմ���
pause >nul
endlocal
