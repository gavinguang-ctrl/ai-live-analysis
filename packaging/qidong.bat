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

echo Starting AI Live Analysis...
echo Browser will open at http://localhost:8501
echo (Close this window to stop the program.)
echo.
"%PY%" -m streamlit run "%~dp0app\app.py" --server.headless=false --server.port=8501
pause
