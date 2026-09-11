@echo off
REM Agentic-Pilot Windows Shortcut Shim
REM Primary orchestrator is native Python: python main.py --eval
py -3 "%~dp0main.py" --eval 2>nul || python "%~dp0main.py" --eval
