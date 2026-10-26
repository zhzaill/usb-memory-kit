@echo off
cd /d "%~dp0"
title CORTICO SYNC AND VECTORIZE
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0memory-kit\bin\pipeline.ps1" -Serve
echo.
pause
