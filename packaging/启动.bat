@echo off
chcp 65001 >nul
title AI 直播复盘分析
cd /d "%~dp0"

set "PY=%~dp0runtime\python\python.exe"
set "FFBIN=%~dp0ffmpeg\bin"

if not exist "%PY%" (
    echo [未安装] 没有检测到运行环境。请先双击「install.bat」完成安装。
    echo.
    pause
    exit /b 1
)

rem 把内置 ffmpeg 加到 PATH，供 video_analyze.py 调用
set "PATH=%FFBIN%;%PATH%"

echo 正在启动 AI 直播复盘分析，浏览器将自动打开 http://localhost:8501 ...
echo （关闭本窗口即可停止程序）
echo.
"%PY%" -m streamlit run "%~dp0app\app.py" --server.headless=false --server.port=8501
pause
