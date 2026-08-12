@echo off
title Build the installer
cd /d "%~dp0"
echo Checking the package before building the installer...
.venv\Scripts\python.exe verify_build.py
if errorlevel 1 (
  echo.
  echo *** Run Build.bat first.
  pause
  exit /b 1
)

echo.
echo Building Setup.exe...
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss
if errorlevel 1 (
  echo.
  echo *** FAILED. Run Build.bat first so the dist folder exists.
) else (
  echo.
  echo Done: installer\XP-Analyzer-Setup.exe
)
echo.
pause
