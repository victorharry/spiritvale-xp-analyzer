"""Prova que o config vai pro lugar certo nos dois modos.

Existe porque isso ja quebrou: ao enxugar o settings.py eu removi o desvio do
modo empacotado. Rodando pelo fonte nada muda — o bug so aparece no .exe, onde
__file__ mora numa pasta temporaria que some ao close. O usuario veria o app
forget todos os niveis medidos a cada uso, sem nenhuma pista do motivo.
"""
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

falhas = []


def conferir(label, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(label)
    print(f"  {'ok ' if ok else 'ERRO'} {label:<44} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


import settings

print("rodando pelo fonte, o config fica junto do code:")
conferir("ROOT e a pasta do projeto",
         settings.ROOT, Path(__file__).resolve().parent.parent)

print("\nempacotado, vai pro APPDATA (senao some ao close):")
sys.frozen = True                      # finge o .exe
try:
    empacotado = importlib.reload(settings)
    esperado = Path(os.environ.get("APPDATA") or Path.home()) / "XP Analyzer"
    conferir("ROOT fora da pasta temporaria", empacotado.ROOT, esperado)
    conferir("e a pasta existe", empacotado.ROOT.is_dir(), True)
finally:
    del sys.frozen
    importlib.reload(settings)            # devolve o modulo ao normal

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
