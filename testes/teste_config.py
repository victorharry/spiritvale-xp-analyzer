"""Prova que o config vai pro lugar certo nos dois modos.

Existe porque isso ja quebrou: ao enxugar o comum.py eu removi o desvio do
modo empacotado. Rodando pelo fonte nada muda — o bug so aparece no .exe, onde
__file__ mora numa pasta temporaria que some ao fechar. O usuario veria o app
esquecer todos os niveis medidos a cada uso, sem nenhuma pista do motivo.
"""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

falhas = []


def conferir(rotulo, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(rotulo)
    print(f"  {'ok ' if ok else 'ERRO'} {rotulo:<44} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


import comum

print("rodando pelo fonte, o config fica junto do codigo:")
conferir("RAIZ e a pasta do projeto",
         comum.RAIZ, Path(__file__).resolve().parent.parent)

print("\nempacotado, vai pro APPDATA (senao some ao fechar):")
sys.frozen = True                      # finge o .exe
try:
    empacotado = importlib.reload(comum)
    esperado = Path(os.environ.get("APPDATA") or Path.home()) / "XP Analyzer"
    conferir("RAIZ fora da pasta temporaria", empacotado.RAIZ, esperado)
    conferir("e a pasta existe", empacotado.RAIZ.is_dir(), True)
finally:
    del sys.frozen
    importlib.reload(comum)            # devolve o modulo ao normal

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
