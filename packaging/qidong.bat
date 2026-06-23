@echo off
title AI Live Analysis
cd /d "%~dp0"

set "PY=%~dp0runtime\python\python.exe"
set "FFBIN=%~dp0ffmpeg\bin"

if not exist "%PY%" (
    echo [NOT INSTALLED] Runtime not found.
    echo Please run  install.bat  first.
    echo.
    pause
    exit /b 1
)

set "PATH=%FFBIN%;%PATH%"

rem --- pre-launch: write streamlit credentials (skip email prompt) + find free port ---
set "PORT=8501"
del "%~dp0app\_port.txt" >nul 2>&1
"%PY%" "%~dp0app\find_port.py" >nul 2>&1
if exist "%~dp0app\_port.txt" set /p PORT=<"%~dp0app\_port.txt"

echo Starting AI Live Analysis...
echo Browser will open at http://localhost:%PORT%
echo (Close this window to stop the program.)
echo.
"%PY%" -m streamlit run "%~dp0app\app.py" --server.headless=false --server.port=%PORT%
pause
