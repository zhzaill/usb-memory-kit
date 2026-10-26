@echo off
cd /d "%~dp0"
title memory-kit
echo Starting memory-kit ...
echo (embedding engine -^> venv check -^> serve -^> browser opens automatically)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0memory-kit\start.ps1"
echo.
echo memory-kit stopped. Press any key to exit.
pause >nul