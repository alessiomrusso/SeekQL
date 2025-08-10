@echo off
setlocal enabledelayedexpansion

REM =======================
REM SeekQL - One-click build (root venv)
REM =======================
set APP_NAME=SeekQL
set FRONTEND_DIR=app\frontend
set ROOT=%~dp0
cd /d "%ROOT%"

REM 0) Tool checks
where python >nul 2>nul || (echo [ERROR] Python not found in PATH & pause & exit /b 1)
where npm    >nul 2>nul || (echo [ERROR] npm not found in PATH & pause & exit /b 1)

REM 1) Create/activate root venv
if not exist ".venv\Scripts\activate.bat" (
  echo [INFO] Creating virtual environment in .venv ...
  python -m venv .venv
  if errorlevel 1 ( echo [ERROR] venv creation failed. & pause & exit /b 1 )
)
call .venv\Scripts\activate.bat
if errorlevel 1 ( echo [ERROR] Failed to activate .venv. & pause & exit /b 1 )

REM Make sure venv Scripts is at PATH head (Windows Store Python workaround)
set "PATH=%CD%\.venv\Scripts;%PATH%"

REM 2) Install Python deps from ROOT requirements.txt
if not exist "requirements.txt" (
  echo [ERROR] requirements.txt not found in project root.
  echo        Create it and run again.
  pause & exit /b 1
)
echo [INFO] Installing Python dependencies...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 ( echo [ERROR] Python dependency install failed. & pause & exit /b 1 )

REM Ensure pyinstaller is available
where pyinstaller >nul 2>nul || (
  echo [INFO] Installing PyInstaller...
  pip install pyinstaller
  if errorlevel 1 ( echo [ERROR] PyInstaller install failed. & pause & exit /b 1 )
)
echo [OK] PyInstaller: 
pyinstaller --version

REM 3) Build frontend (Vite)
echo.
echo [INFO] Building frontend...
pushd "%FRONTEND_DIR%"
call npm install
if errorlevel 1 ( echo [ERROR] npm install failed. & popd & pause & exit /b 1 )
call npm run build
if errorlevel 1 ( echo [ERROR] npm run build failed. & popd & pause & exit /b 1 )
popd

REM 4) Package EXE (run from ROOT; add-data uses ROOT-relative paths)
echo.
echo [INFO] Packaging %APP_NAME%.exe ...
pyinstaller ^
  --onefile ^
  --name %APP_NAME% ^
  --add-data "lib/opensearch;opensearch" ^
  --add-data "app/frontend/dist;frontend_dist" ^
  --add-data "app/backend;backend" ^
  --hidden-import fastapi ^
  --hidden-import uvicorn ^
  --hidden-import opensearchpy ^
  launcher.py

if errorlevel 1 (
  echo [ERROR] PyInstaller build failed.
  pause & exit /b 1
)

echo.
echo [OK] Build completed.
echo EXE: dist\%APP_NAME%.exe
pause
endlocal
