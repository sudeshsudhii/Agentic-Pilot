@echo off
setlocal enabledelayedexpansion

title Pilot Agent Observatory - Port 3001
echo ===================================================
echo   PILOT AGENT OBSERVATORY
echo   Real-Time Telemetry ^& Execution Inspector
echo ===================================================
echo.
echo Dashboard URL: http://127.0.0.1:3001
echo Backend API:   http://127.0.0.1:8766
echo Pilot Core:    http://127.0.0.1:8765
echo.

cd /d "%~dp0"

echo [1/2] Starting Observatory Backend (port 8766)...
start "Observatory Backend" /min cmd /c "python -m observatory.backend.main"

timeout /t 2 /nobreak >nul

echo [2/2] Starting Observatory Frontend (port 3001)...
cd /d "%~dp0observatory\frontend"
if not exist node_modules (
    echo Installing frontend dependencies...
    call npm install
)

start "Observatory Frontend :3001" cmd /c "npm run dev"

timeout /t 3 /nobreak >nul
echo.
echo Observatory is live at http://127.0.0.1:3001
echo.
start http://127.0.0.1:3001
pause
