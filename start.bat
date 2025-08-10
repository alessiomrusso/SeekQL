@echo off
setlocal ENABLEEXTENSIONS
set "SCRIPT_DIR=%~dp0"

call "%SCRIPT_DIR%start_opensearch.bat"
timeout /t 7 >nul

call "%SCRIPT_DIR%start_backend.bat"
timeout /t 3 >nul

call "%SCRIPT_DIR%start_frontend.bat"

echo.
echo [OK] Windows opened:
echo   - "OpenSearch"
echo   - "Backend (Uvicorn)"
echo   - "Frontend (Vite)"
echo If Frontend didn't open, see: app\frontend\vite-start.log
echo.
pause
