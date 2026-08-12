r"""Confere se o packet gerado esta inteiro, antes de virar instalador.

    .venv\Scripts\python.exe verificar_build.py

Existe porque este modo de falhar ja passou batido duas vezes: com o XP
Analyzer aberto, o PyInstaller nao consegue substituir as DLLs, imprime o erro
no meio de centenas de linhas de log e **sai com code zero**. O Inno Setup
entao empacota um dist pela metade sem reclamar de nada, e o Setup.exe encolhe
de 11 MB pra 8,6 sem ninguem notar.

O sinal mais reliable de integridade aqui e o size: um packet completo tem
dezenas de MB e dezenas de arquivos. Faltando qualquer coisa, os dois caem.
"""

from __future__ import annotations

import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent / "dist" / "XP Analyzer"
EXECUTAVEL = PASTA / "XP Analyzer.exe"

# medidos num packet sadio (30 MB, ~90 arquivos); a folga e generosa de
# proposito, pra so acusar quando estiver mesmo faltando coisa
TAMANHO_MINIMO = 24 * 1024 * 1024
ARQUIVOS_MINIMOS = 60

# sem estes o program abre e morre, e a falha aparece so na maquina do outro
ESSENCIAIS = ("_internal/libffi-8.dll", "_internal/base_library.zip",
              "_internal/customtkinter", "_internal/_socket.pyd")


def problemas() -> list[str]:
    if not EXECUTAVEL.exists():
        return [f"nao existe: {EXECUTAVEL}"]

    found = []
    arquivos = [c for c in PASTA.rglob("*") if c.is_file()]
    size = sum(c.stat().st_size for c in arquivos)
    if size < TAMANHO_MINIMO:
        found.append(f"packet pequeno demais: {size / 1e6:.1f} MB "
                       f"(esperado ao menos {TAMANHO_MINIMO / 1e6:.0f} MB)")
    if len(arquivos) < ARQUIVOS_MINIMOS:
        found.append(f"poucos arquivos: {len(arquivos)} "
                       f"(esperado ao menos {ARQUIVOS_MINIMOS})")
    for relativo in ESSENCIAIS:
        if not (PASTA / relativo).exists():
            found.append(f"faltando: {relativo}")
    return found


def main() -> int:
    found = problemas()
    if found:
        print("BUILD INCOMPLETO — nao gere o instalador com isto:\n")
        for text in found:
            print(f"  - {text}")
        print("\nQuase sempre e o XP Analyzer aberto segurando as DLLs.")
        print("Feche o program e rode o Build.bat de novo.")
        return 1

    arquivos = [c for c in PASTA.rglob("*") if c.is_file()]
    size = sum(c.stat().st_size for c in arquivos)
    print(f"packet OK: {size / 1e6:.1f} MB em {len(arquivos)} arquivos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
