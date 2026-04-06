@echo off
chcp 65001 >nul 2>&1
title AGARS Installer
echo.
echo Starting AGARS installer...
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Installation script failed with error code %errorlevel%
    echo.
)
echo.
echo Press any key to exit...
pause >nul
