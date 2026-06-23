@echo off
title AI Live Analysis - Install
echo.
echo ============================================================
echo    AI Live Analysis - First-time setup
echo.
echo    Downloads portable Python + dependencies + ffmpeg.
echo    Internet required. Everything installs into THIS folder.
echo ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\setup.ps1"
if errorlevel 1 (
    echo.
    echo [FAILED] Setup did not finish. Screenshot the error above.
    echo Most common cause: cannot reach GitHub. Turn on a proxy/VPN and retry.
    echo.
    pause
    exit /b 1
)
echo.
echo Done. Now double-click  qidong.bat  (the launcher) to start.
echo.
pause
