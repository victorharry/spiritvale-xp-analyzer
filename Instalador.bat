@echo off
title Gerar o instalador
cd /d "%~dp0"
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
