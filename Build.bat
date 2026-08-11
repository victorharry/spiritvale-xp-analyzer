@echo off
title Build do XP Analyzer
cd /d "%~dp0"

echo Fechando o XP Analyzer, se estiver aberto...
taskkill /IM "XP Analyzer.exe" /F >nul 2>&1
timeout /t 3 /nobreak >nul

echo.
echo Conferindo os testes antes de empacotar...
for %%T in (teste_personagem teste_rede teste_nivel teste_config teste_tabela) do (
  .venv\Scripts\python.exe testes\%%T.py >nul 2>&1
  if errorlevel 1 (
    echo *** %%T FALHOU. Build cancelado.
    pause
    exit /b 1
  )
  echo    %%T ok
)

echo.
echo Gerando o executavel...
rem A configuracao toda vive no .spec — nao repita opcoes aqui, senao as duas
rem versoes divergem e o build passa a depender de por onde foi chamado.
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean "XP Analyzer.spec"
if errorlevel 1 (
  echo.
  echo *** DEU ERRO no build. A saida acima diz o motivo.
  pause
  exit /b 1
)

echo.
echo Pronto: dist\XP Analyzer\XP Analyzer.exe
echo Para gerar o instalador, rode o Instalador.bat
echo.
pause
