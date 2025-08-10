@echo off
setlocal
cd /d "%~dp0"

set "VENV=.venv"

REM Create venv if missing
if not exist "%VENV%\Scripts\python.exe" (
  echo [INFO] Creating venv...
  python -m venv "%VENV%" || python -m venv "%VENV%"
)

REM Activate venv
call "%VENV%\Scripts\activate.bat"

REM If requirements.txt exists, install/update deps
if exist "requirements.txt" (
  echo [INFO] Installing/updating dependencies...
  pip install -r requirements.txt
)

REM Start backend in a new window
start "SeekQL Backend (Uvicorn)" cmd /k python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000 --reload

exit /b 0
