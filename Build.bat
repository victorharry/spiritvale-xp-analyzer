@echo off
title XP Analyzer build
cd /d "%~dp0"

echo Closing the XP Analyzer if it is running...
taskkill /IM "XP Analyzer.exe" /F >nul 2>&1
timeout /t 3 /nobreak >nul

echo.
echo Running the tests before packaging...
for %%T in (test_character test_network test_levels test_config test_xp_table test_capture test_updates test_coins) do (
  .venv\Scripts\python.exe tests\%%T.py >nul 2>&1
  if errorlevel 1 (
    echo *** %%T FAILED. Build cancelled.
    pause
    exit /b 1
  )
  echo    %%T ok
)

echo.
echo Building the executable...
rem All configuration lives in the .spec — do not repeat options here, or the
rem two copies drift and the build starts depending on how it was invoked.
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean "XP Analyzer.spec"
if errorlevel 1 (
  echo.
  echo *** BUILD FAILED. The output above says why.
  pause
  exit /b 1
)

echo.
echo Checking that the package came out complete...
.venv\Scripts\python.exe verify_build.py
if errorlevel 1 (
  echo.
  pause
  exit /b 1
)

echo.
echo Done: dist\XP Analyzer\XP Analyzer.exe
echo To build the installer, run Installer.bat
echo.
pause
