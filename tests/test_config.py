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

print("\no instalador precisa enxergar que o app esta aberto:")
# Sem isto, instalar por cima de uma copia aberta falha no MEIO da copia, em
# "DeleteFile failed; code 5", com o usuario escolhendo entre tentar de novo e
# uma instalacao pela metade. O nome tem que bater com o AppMutex do
# installer.iss, e o mutex tem que ser visivel de FORA deste processo.
import ctypes
import re

SYNCHRONIZE = 0x00100000


def enxerga(nome):
    h = ctypes.windll.kernel32.OpenMutexW(SYNCHRONIZE, False, nome)
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
    return bool(h)


nome_local = settings.MUTEX_NAME
nome_global = f"Global\\{nome_local}"
conferir("nao existe antes de anunciar", enxerga(nome_local), False)
settings.announce_running()
conferir("o local fica visivel", enxerga(nome_local), True)
conferir("o global tambem", enxerga(nome_global), True)
settings.announce_running()               # chamar duas vezes nao duplica nada
conferir("anunciar de novo nao acumula", len(settings._mutexes), 2)

iss = Path(__file__).resolve().parent.parent / "installer.iss"
if iss.exists():
    achado = re.search(r"^AppMutex=(.+)$",
                       iss.read_text(encoding="utf-8", errors="replace"),
                       re.MULTILINE)
    declarados = [n.strip() for n in achado.group(1).split(",")] if achado else []
    conferir("installer.iss procura os mesmos nomes",
             declarados, [nome_global, nome_local])
else:
    print("  (installer.iss nao encontrado, pulando)")

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
