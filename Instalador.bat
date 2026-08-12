@echo off
title Gerar o instalador
cd /d "%~dp0"
echo Conferindo o pacote antes de empacotar...
.venv\Scripts\python.exe verificar_build.py
if errorlevel 1 (
  echo.
  echo *** Rode o Build.bat primeiro.
  pause
  exit /b 1
)

echo.
echo Gerando o Setup.exe...
"%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" instalador.iss
if errorlevel 1 (
  echo.
  echo *** DEU ERRO. Rode o Build.bat antes, pra ter a pasta dist.
) else (
  echo.
  echo Pronto: instalador\XP-Analyzer-Setup.exe
)
echo.
pause
