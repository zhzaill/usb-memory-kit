@echo off
cd /d "%~dp0"
title memory-kit browser
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0open-kit.ps1"
if errorlevel 1 pause