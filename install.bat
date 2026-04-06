@echo off
chcp 65001 >nul 2>&1
title AGARS Installer
echo.
echo Starting AGARS installer...
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0install.ps1"
