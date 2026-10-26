@echo off
cd /d "%~dp0"
title MEMORY KIT LAUNCHER
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0browser\open-kit.ps1"
if errorlevel 1 pause
