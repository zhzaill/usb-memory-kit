@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0memory-kit\bin\pipeline.ps1"
pause
