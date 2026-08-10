@echo off
title Build do XP Analyzer
cd /d "%~dp0"
echo Fechando o XP Analyzer, se estiver aberto...
taskkill /IM "XP Analyzer.exe" /F >/dev/null 2>&1
timeout /t 2 /nobreak >nul
echo.
echo Gerando o executavel (leva uns 10 segundos)...
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --name "XP Analyzer" --collect-data customtkinter --hidden-import PIL._tkinter_finder --exclude-module matplotlib --exclude-module pandas --exclude-module pytesseract xp_analyzer.py
if errorlevel 1 (
  echo.
  echo *** DEU ERRO no build. A saida acima diz o motivo.
) else (
  echo.
  echo Pronto: dist\XP Analyzer\XP Analyzer.exe
)
echo.
pause
