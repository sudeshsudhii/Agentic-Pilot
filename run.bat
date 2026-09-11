@echo off
REM Agentic-Pilot Windows Shortcut Shim
REM Primary orchestrator is native Python: python main.py
py -3 "%~dp0main.py" %* 2>nul || python "%~dp0main.py" %*
