@echo off
echo [*] 기존 Flask 프로세스 종료 중...
taskkill /F /IM python.exe /T 2>nul
timeout /t 1 >nul

echo [*] Flask 서버 시작 (포트 5000)...
cd /d "%~dp0"
start "" python app.py

echo [OK] http://localhost:5000 에서 실행 중입니다.
