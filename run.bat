@echo off
setlocal enabledelayedexpansion

:: Force UTF-8 encoding for clean console rendering
chcp 65001 >nul 2>&1

:: Resolve directory to project root
set "PILOT_ROOT=%~dp0"
cd /d "%PILOT_ROOT%"

title Agentic Pilot - Launcher ^& Process Manager

:: ============================================================================
:: 1. LOCATE PYTHON INTERPRETER
:: ============================================================================
set "PYTHON_EXE="

if exist "%PILOT_ROOT%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PILOT_ROOT%.venv\Scripts\python.exe"
) else if exist "%PILOT_ROOT%venv\Scripts\python.exe" (
    set "PYTHON_EXE=%PILOT_ROOT%venv\Scripts\python.exe"
) else (
    where py >nul 2>&1
    if !errorlevel! equ 0 (
        set "PYTHON_EXE=py -3"
    ) else (
        where python >nul 2>&1
        if !errorlevel! equ 0 (
            set "PYTHON_EXE=python"
        )
    )
)

if "%PYTHON_EXE%"=="" (
    echo.
    echo ======================================================================
    echo [ERROR] Python was not found on your system PATH!
    echo ======================================================================
    echo Please install Python 3.10+ from https://www.python.org/
    echo Remember to check "Add Python to PATH" during installation.
    echo ======================================================================
    echo.
    pause
    exit /b 1
)

:: ============================================================================
:: 2. ENVIRONMENT FILE INITIALIZATION (.env)
:: ============================================================================
if not exist "%PILOT_ROOT%.env" (
    if exist "%PILOT_ROOT%.env.example" (
        echo [INFO] Creating .env from .env.example
        copy /y "%PILOT_ROOT%.env.example" "%PILOT_ROOT%.env" >nul
    )
)

:: ============================================================================
:: 3. NODE.JS / FRONTEND PREREQUISITES
:: ============================================================================
where npm >nul 2>&1
if !errorlevel! equ 0 (
    if not exist "%PILOT_ROOT%frontend\node_modules" (
        echo [INFO] Installing frontend dependencies via npm install...
        pushd "%PILOT_ROOT%frontend"
        call npm install --silent
        popd
    )
)

:: ============================================================================
:: 4. DIRECT CLI ARGUMENT PASSTHROUGH
:: ============================================================================
:: If arguments were supplied (e.g. run.bat --backend-only, run.bat --stop, etc.)
if not "%~1"=="" (
    %PYTHON_EXE% "%PILOT_ROOT%main.py" %*
    if !errorlevel! neq 0 (
        echo.
        echo [ERROR] Process exited with error code !errorlevel!.
        pause
    )
    exit /b !errorlevel!
)

:: ============================================================================
:: 5. INTERACTIVE LAUNCHER MENU
:: ============================================================================
:MENU
cls
echo ======================================================================
echo                 AGENTIC PILOT - RUNTIME LAUNCHER
echo               Autonomous Multi-Environment AI Agent
echo ======================================================================
echo.
echo   Active LLM Provider : Google Gemini API (gemini-2.5-flash) [DEFAULT]
echo   Fallback Runtime    : Local Ollama Models (qwen2.5 / moondream)
echo   Local Web UI        : http://127.0.0.1:1420
echo   Backend REST API    : http://127.0.0.1:8765
echo.
echo ----------------------------------------------------------------------
echo   LAUNCH OPTIONS:
echo ----------------------------------------------------------------------
echo   [1] Start Agentic Pilot (Frontend + Backend + Gemini API)  [DEFAULT]
echo   [2] Start Full System + Observatory Telemetry Dashboard (:3001)
echo   [3] Start Backend Server Only (:8765)
echo   [4] Stop All Running Pilot Services ^& Clear Ports
echo   [5] Run Full Automated Regression Test Suite
echo   [6] Run Performance Evaluation Benchmarks ^& Report
echo   [7] Configure .env Settings in Notepad
echo   [8] Exit Launcher
echo ======================================================================
echo.

set "CHOICE="
set /p "CHOICE=Enter choice [1-8] (Press Enter for Default 1): "
if defined CHOICE set "CHOICE=%CHOICE: =%"
if not defined CHOICE set "CHOICE=1"

if "%CHOICE%"=="1" goto START_DEFAULT
if "%CHOICE%"=="2" goto START_OBSERVATORY
if "%CHOICE%"=="3" goto START_BACKEND
if "%CHOICE%"=="4" goto STOP_SERVICES
if "%CHOICE%"=="5" goto RUN_TESTS
if "%CHOICE%"=="6" goto RUN_EVAL
if "%CHOICE%"=="7" goto EDIT_ENV
if "%CHOICE%"=="8" goto EXIT_APP

echo.
echo [WARNING] Invalid choice "%CHOICE%". Defaulting to Option 1.
timeout /t 2 >nul
goto START_DEFAULT

:START_DEFAULT
echo.
echo [INFO] Starting Agentic Pilot (Backend + Frontend)...
%PYTHON_EXE% "%PILOT_ROOT%main.py"
goto CHECK_EXIT

:START_OBSERVATORY
echo.
echo [INFO] Starting Agentic Pilot with Observatory Telemetry (:3001)...
%PYTHON_EXE% "%PILOT_ROOT%main.py" --observatory
goto CHECK_EXIT

:START_BACKEND
echo.
echo [INFO] Starting Pilot Backend API server only (:8765)...
%PYTHON_EXE% "%PILOT_ROOT%main.py" --backend-only
goto CHECK_EXIT

:STOP_SERVICES
echo.
echo [INFO] Stopping all Pilot background processes and clearing ports...
%PYTHON_EXE% "%PILOT_ROOT%main.py" --stop
echo.
pause
goto MENU

:RUN_TESTS
echo.
echo [INFO] Running automated regression test suite...
%PYTHON_EXE% "%PILOT_ROOT%main.py" --test
echo.
pause
goto MENU

:RUN_EVAL
echo.
echo [INFO] Running research evaluation benchmarks...
%PYTHON_EXE% "%PILOT_ROOT%main.py" --eval
echo.
pause
goto MENU

:EDIT_ENV
if exist "%PILOT_ROOT%.env" (
    start notepad "%PILOT_ROOT%.env"
) else (
    echo [ERROR] .env file not found.
)
goto MENU

:CHECK_EXIT
if !errorlevel! neq 0 (
    echo.
    echo ======================================================================
    echo [ERROR] Agentic Pilot exited with code !errorlevel!.
    echo ======================================================================
    echo If you encountered an issue, check the logs or run:
    echo   run.bat --stop
    echo to clear stale background processes.
    echo ======================================================================
    echo.
    pause
)
goto EXIT_APP

:EXIT_APP
exit /b 0
