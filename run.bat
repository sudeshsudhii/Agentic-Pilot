@echo off
title Agentic-Pilot Launcher

echo.
echo  ============================================
echo    Agentic-Pilot  -  Local AI Browser Agent
echo  ============================================
echo.

set "ROOT=%~dp0"
set "VENV=%ROOT%venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "FRONTEND=%ROOT%frontend"
set "BACKEND_PORT=8765"
set "FRONTEND_PORT=1420"
set "OLLAMA_URL=http://127.0.0.1:11434"
set "TEXT_MODEL=qwen2.5:1.5b"
set "VISION_MODEL=moondream"

REM --- Locate Ollama (before enabledelayedexpansion to avoid ! issues) ---
set "OLLAMA_EXE="
where ollama >nul 2>&1
if %errorlevel% equ 0 (
    for /f "delims=" %%i in ('where ollama') do set "OLLAMA_EXE=%%i"
)
if "%OLLAMA_EXE%" == "" (
    if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" (
        set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
    )
)

REM Enable delayed expansion AFTER setting OLLAMA_EXE
setlocal enabledelayedexpansion

REM ====================================================
REM  Step 0: Kill stale processes on ports
REM ====================================================
echo  [0/6] Clearing stale processes on ports %BACKEND_PORT% and %FRONTEND_PORT%...
for %%P in (%BACKEND_PORT% %FRONTEND_PORT%) do (
    for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%%P" 2^>nul') do (
        if "%%p" neq "0" (
            taskkill /PID %%p /F >nul 2>&1
        )
    )
)
ping 127.0.0.1 -n 2 >nul
echo        Done.
echo.

REM ====================================================
REM  Step 1: Verify Python venv
REM ====================================================
echo  [1/6] Checking Python virtual environment...
if not exist "%PYTHON%" (
    echo.
    echo  ERROR: Python venv not found at %VENV%
    echo         Run: python -m venv venv
    echo         Then: venv\Scripts\pip install -r backend\requirements.txt
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%v in ('"%PYTHON%" --version 2^>^&1') do set "PYVER=%%v"
echo        Found: %PYVER%
echo.

REM ====================================================
REM  Step 2: Check and start Ollama
REM ====================================================
echo  [2/6] Checking Ollama service...

if "%OLLAMA_EXE%" == "" (
    echo.
    echo  WARNING: Ollama executable not found.
    echo           Install from https://ollama.com/download
    echo           The backend will start but AI features will NOT work.
    echo.
    goto :skip_ollama
)

echo        Found: %OLLAMA_EXE%

REM Check if Ollama API is already responding
powershell -NonInteractive -NoProfile -InputFormat None -Command "try { Invoke-WebRequest -Uri '%OLLAMA_URL%/api/tags' -UseBasicParsing -TimeoutSec 3 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if !errorlevel! equ 0 (
    echo        Ollama is already running.
) else (
    echo        Ollama is not running. Starting it now...
    start "Ollama Service" /min "%OLLAMA_EXE%" serve
    echo        Waiting for Ollama to be ready...

    set "OLLAMA_READY=0"
    for /l %%i in (1,1,20) do (
        if !OLLAMA_READY! equ 0 (
            ping 127.0.0.1 -n 2 >nul
            powershell -NonInteractive -NoProfile -InputFormat None -Command "try { Invoke-WebRequest -Uri '%OLLAMA_URL%/api/tags' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
            if !errorlevel! equ 0 (
                set "OLLAMA_READY=1"
                echo        Ollama is ready. ^(%%i seconds^)
            )
        )
    )
    if !OLLAMA_READY! equ 0 (
        echo.
        echo  WARNING: Ollama did not respond after 20 seconds.
        echo           AI features may not work.
        echo.
        goto :skip_ollama
    )
)
echo.

REM ====================================================
REM  Step 3: Ensure required models are pulled
REM ====================================================
echo  [3/6] Checking AI models...

REM Check text model
"%OLLAMA_EXE%" list 2>nul | findstr /i "%TEXT_MODEL%" >nul 2>&1
if !errorlevel! neq 0 (
    echo        Pulling text model: %TEXT_MODEL% ^(this may take a few minutes^)...
    "%OLLAMA_EXE%" pull %TEXT_MODEL%
    if !errorlevel! neq 0 (
        echo  WARNING: Failed to pull %TEXT_MODEL%.
    ) else (
        echo        %TEXT_MODEL% pulled successfully.
    )
) else (
    echo        Text model ready: %TEXT_MODEL%
)

REM Check vision model
"%OLLAMA_EXE%" list 2>nul | findstr /i "%VISION_MODEL%" >nul 2>&1
if !errorlevel! neq 0 (
    echo        Pulling vision model: %VISION_MODEL% ^(this may take a few minutes^)...
    "%OLLAMA_EXE%" pull %VISION_MODEL%
    if !errorlevel! neq 0 (
        echo  WARNING: Failed to pull %VISION_MODEL%. Vision fallback will not work.
    ) else (
        echo        %VISION_MODEL% pulled successfully.
    )
) else (
    echo        Vision model ready: %VISION_MODEL%
)
echo.

:skip_ollama

REM ====================================================
REM  Step 4: Verify Playwright browsers
REM ====================================================
echo  [4/6] Checking Playwright browsers...
"%PYTHON%" -c "from playwright.sync_api import sync_playwright; p=sync_playwright().start(); b=p.chromium.launch(headless=True); b.close(); p.stop(); print('OK')" >nul 2>&1
if !errorlevel! neq 0 (
    echo        Playwright browsers not installed. Installing Chromium...
    "%PYTHON%" -m playwright install chromium
    if !errorlevel! neq 0 (
        echo  WARNING: Playwright browser install failed.
        echo           Browser automation will not work.
    ) else (
        echo        Chromium installed successfully.
    )
) else (
    echo        Chromium is ready.
)
echo.

REM ====================================================
REM  Step 5: Start Backend
REM ====================================================
echo  [5/6] Starting Backend Server...
start "Pilot Backend" cmd /k "title Pilot Backend && cd /d "%ROOT%" && call "%VENV%\Scripts\activate.bat" && set PYTHONPATH=%ROOT%&& python backend\main.py"

REM Wait a moment for backend to bind the port
ping 127.0.0.1 -n 4 >nul

REM Verify backend is responding
powershell -NonInteractive -NoProfile -InputFormat None -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8765/health' -UseBasicParsing -TimeoutSec 3; exit 0 } catch { exit 1 }" >nul 2>&1
if !errorlevel! equ 0 (
    echo        Backend is running on http://127.0.0.1:%BACKEND_PORT%
) else (
    echo        Backend starting... ^(check the Pilot Backend window for details^)
)
echo.

REM ====================================================
REM  Step 6: Start Frontend
REM ====================================================
echo  [6/6] Starting Frontend Web Server...

REM Check node_modules exist
if not exist "%FRONTEND%\node_modules" (
    echo        Installing frontend dependencies...
    start /wait "npm install" cmd /c "cd /d "%FRONTEND%" && npm install"
)

start "Pilot Frontend" cmd /k "title Pilot Frontend && cd /d "%FRONTEND%" && npm run dev"

echo        Frontend starting on http://127.0.0.1:%FRONTEND_PORT%
echo.

REM ====================================================
REM  Summary
REM ====================================================
echo  ============================================
echo    All services launched.
echo.
echo    Frontend UI : http://127.0.0.1:%FRONTEND_PORT%
echo    Backend API : http://127.0.0.1:%BACKEND_PORT%
echo    Ollama      : %OLLAMA_URL%
echo.
echo    Text Model  : %TEXT_MODEL%
echo    Vision Model: %VISION_MODEL%
echo  ============================================
echo.
echo  Three windows opened:
echo    - Pilot Backend  ^(FastAPI + LangGraph^)
echo    - Pilot Frontend ^(Vite + React^)
echo    - Ollama Service ^(if auto-started^)
echo.
echo  Close those windows to stop the services.
echo.
pause
