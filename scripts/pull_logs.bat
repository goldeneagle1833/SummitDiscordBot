@echo off
REM Simple batch wrapper for pulling logs
REM Usage: scripts\pull_logs.bat

echo Pulling logs from server...
powershell -ExecutionPolicy Bypass -File "%~dp0pull_logs.ps1"
pause
