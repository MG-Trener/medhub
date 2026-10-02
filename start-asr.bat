@echo off
setlocal
title medhub ASR - port 8090
echo Starting medhub ASR. Keep this window open while using speech recognition.
echo Press Ctrl+C to stop the server.
echo The VPN connection must be active if ASR is bound to a VPN address.
echo.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\gpu\windows\start-asr.ps1"
set "asrExitCode=%ERRORLEVEL%"
echo.
echo ASR stopped. Exit code: %asrExitCode%
echo Press any key to close this window.
pause >nul
exit /b %asrExitCode%
