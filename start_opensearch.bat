@echo off
setlocal ENABLEEXTENSIONS
set "SCRIPT_DIR=%~dp0"
set "OPENSEARCH_DIR=%SCRIPT_DIR%lib\opensearch"

if not exist "%OPENSEARCH_DIR%\bin\opensearch.bat" (
  echo [ERROR] Not found: "%OPENSEARCH_DIR%\bin\opensearch.bat"
  echo Put the extracted OpenSearch in: %OPENSEARCH_DIR%
  pause & exit /b 1
)

echo [INFO] Starting OpenSearch...
start "OpenSearch" cmd /k "%OPENSEARCH_DIR%\bin\opensearch.bat"
exit /b 0
