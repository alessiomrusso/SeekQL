@echo off
setlocal ENABLEEXTENSIONS
set "SCRIPT_DIR=%~dp0"
set "FRONT_DIR=%SCRIPT_DIR%app\frontend"
set "LOG=%FRONT_DIR%\vite-start.log"

echo [INFO] Frontend dir: "%FRONT_DIR%"

REM 1) Check folder & package.json
if not exist "%FRONT_DIR%\package.json" (
  echo [ERROR] Not found: %FRONT_DIR%\package.json
  pause & exit /b 1
)

REM 2) Check Node and npm on PATH
where node >nul 2>&1 || (echo [ERROR] Node.js not on PATH & pause & exit /b 1)
where npm  >nul 2>&1 || (echo [ERROR] npm not on PATH & pause & exit /b 1)

REM 3) Install deps (log output)
pushd "%FRONT_DIR%"
echo [INFO] npm install (first run may take a while)...
call npm install > "%LOG%" 2>&1 || (
  echo [ERROR] npm install failed. See %LOG%
  type "%LOG%" | more
  popd & pause & exit /b 1
)
popd

REM 4) Start Vite in a NEW window, set working dir via /D, keep console open
start "Frontend (Vite)" cmd /k cd  /d "%FRONT_DIR%" ^&^& call npm run dev

echo [OK] Frontend start requested.
exit /b 0
