@echo off
setlocal enabledelayedexpansion

title Pilot ^& Agent Observatory Launcher
echo ===================================================
echo   PILOT ^& PILOT AGENT OBSERVATORY
echo ===================================================
echo.
echo Pilot Web UI:          http://127.0.0.1:1420
echo Pilot Backend:         http://127.0.0.1:8765
echo Observatory Dashboard: http://127.0.0.1:3001
echo Observatory Backend:   http://127.0.0.1:8766
echo.

cd /d "%~dp0"

echo [1/2] Launching Pilot Agent (Backend + Frontend)...
start "Pilot Launcher" cmd /c "python main.py --no-browser"

timeout /t 5 /nobreak >nul

echo [2/2] Launching Pilot Agent Observatory...
call "%~dp0start_observatory.bat"
