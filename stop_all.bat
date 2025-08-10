@echo off
setlocal ENABLEEXTENSIONS
set "SCRIPT_DIR=%~dp0"

call "%SCRIPT_DIR%start_opensearch.bat"
timeout /t 7 >nul

call "%SCRIPT_DIR%setup_backend.bat"
call "%SCRIPT_DIR%start_backend.bat"
timeout /t 3 >nul

call "%SCRIPT_DIR%start_frontend.bat"

echo.
echo [OK] Services started (if no errors above).
echo - OpenSearch:  http://localhost:9200
echo - Backend:     http://localhost:8000/health
echo - Frontend:    http://localhost:3000
echo.
pause
