@echo off
chcp 65001 >nul
title ORB Scanner
cd /d "%~dp0"

echo ==========================================
echo   Starting US Market ORB Scanner...
echo ==========================================
echo.

REM 1) تشغيل سيرفر اللوحة في نافذة منفصلة
start "ORB Dashboard Server" /min python -m http.server 8777 --directory docs

REM 2) انتظار ثانيتين حتى يجهز السيرفر قبل فتح المتصفح
timeout /t 2 /nobreak >nul

REM 3) فتح اللوحة في المتصفح
start "" http://localhost:8777

REM 4) تشغيل المراقب في هذه النافذة (اتركها مفتوحة)
python watch.py 5

pause
