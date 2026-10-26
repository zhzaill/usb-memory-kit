@echo off
cd /d "%~dp0"
title CORTICO FIELD CONSOLE
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0console.ps1"
if errorlevel 1 pause
