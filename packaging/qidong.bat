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

rem --- find first free port starting at 8501 (auto-skip if occupied) ---
set "PORT=8501"
for /f "usebackq delims=" %%p in (`"%PY%" "%~dp0app\find_port.py"`) do set "PORT=%%p"

echo Starting AI Live Analysis...
echo Browser will open at http://localhost:%PORT%
echo (Close this window to stop the program.)
echo.
"%PY%" -m streamlit run "%~dp0app\app.py" --server.headless=false --server.port=%PORT%
pause
