@echo off
cd /d "%~dp0"
title memory-kit absorb
echo ============================================================
echo   memory-kit :: absorb the logs of THIS machine
echo ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0memory-kit\bin\pipeline.ps1"
echo.
pause