@echo off
echo =========================================
echo        Starting Agentic-Pilot
echo =========================================

echo.
echo [1/2] Starting Backend Server...
start "Pilot Backend" cmd /k "cd /d %~dp0 && venv\Scripts\python.exe backend\main.py"

echo.
echo [2/2] Starting Frontend Web Server...
start "Pilot Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

echo.
echo Both services are now launching in separate windows!
echo - Frontend UI will be available at http://localhost:1420
echo - Backend API is running on http://localhost:8765
echo.
echo Close those windows to stop the servers when you are done.
