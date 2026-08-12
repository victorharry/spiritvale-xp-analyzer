"""Confere a tabela de XP extraida do jogo contra as medicoes independentes.

A tabela veio dos arquivos do cliente; as medicoes vieram de ler a barra e
cruzar com o XP dos packets. Sao duas fontes que nao se falam — se batem, as
duas estao certas.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import xp_table

falhas = []


def conferir(label, obtido, esperado):
    ok = obtido == esperado
    if not ok:
        falhas.append(label)
    print(f"  {'ok ' if ok else 'ERRO'} {label:<46} {obtido!r}"
          + ("" if ok else f"  (esperado {esperado!r})"))


# faixas medidas pelo painel de calibracao (ver NOTAS-XP.md)
MEDIDO = {
    16: (29669, 29699), 17: (36101, 36197), 18: (43482, 43568),
    19: (51895, 51959), 20: (61415, 61511), 21: (72055, 72079),
    22: (83830, 83880), 23: (96816, 97020), 24: (110536, 111390),
    25: (126648, 126662), 26: (143453, 143629), 28: (181215, 181462),
    33: (303101, 303121), 35: (365348, 367503), 71: (4525421, 4526623),
    114: (39227811, 39324526), 116: (42952473, 43198619),
}

print("a tabela do jogo cai dentro de cada faixa medida:")
for level, (baixo, alto) in sorted(MEDIDO.items()):
    valor = xp_table.xp_for_level(level)
    conferir(f"level {level} = {valor:,}", baixo <= valor <= alto, True)

print("\nsanidade da tabela:")
conferir("cobre ate 161 (o jogo satura em 2^31 depois)",
         xp_table.HIGHEST_LEVEL, 161)
conferir("level 1 custa 40", xp_table.xp_for_level(1), 40)
conferir("so cresce",
         all(xp_table.XP_PER_LEVEL[i] < xp_table.XP_PER_LEVEL[i + 1]
             for i in range(xp_table.HIGHEST_LEVEL - 1)), True)
conferir("level 0 nao existe", xp_table.xp_for_level(0), None)
conferir("acima da tabela devolve None", xp_table.xp_for_level(200), None)

print("\n" + ("FALHAS: " + ", ".join(falhas) if falhas else "TUDO OK"))
sys.exit(1 if falhas else 0)
