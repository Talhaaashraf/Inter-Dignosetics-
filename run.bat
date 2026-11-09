@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" main.py
) else if exist "Scripts\python.exe" (
  "Scripts\python.exe" main.py
) else (
  python main.py
)
if errorlevel 1 (
  echo Application exited with an error. See logs\application.log.
  pause
)
