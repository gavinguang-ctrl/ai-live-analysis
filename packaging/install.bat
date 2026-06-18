@echo off
chcp 65001 >nul
title AI 直播复盘分析 — 安装环境
echo.
echo ============================================================
echo    AI 直播复盘分析 — 首次安装
echo    将下载便携版 Python + 依赖 + ffmpeg（全部装在本文件夹）
echo    需要联网；安装完成后即可离线使用（API 调用除外）
echo ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0packaging\setup.ps1"
if errorlevel 1 (
    echo.
    echo [安装失败] 请把上面的红色错误信息截图反馈。常见原因：网络无法访问 GitHub。
    echo.
    pause
    exit /b 1
)
echo.
pause
