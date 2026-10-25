@echo off
setlocal
cd /d "%~dp0"
echo Starting on-stick local AI (chat 18080 / embedding 18082) ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-local-ai.ps1"
echo.
echo Close this window or run start-local-ai.ps1 -Stop to stop the servers.
pause