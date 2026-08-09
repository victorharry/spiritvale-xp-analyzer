"""Entre os candidatos que sobraram, acha o par (XP atual, XP do nivel).

A porcentagem da barra e a prova final: se um campo e o XP atual e outro e o
XP necessario pro proximo nivel, a divisao tem que dar exatamente o que a
barra mostra. Coincidencia numerica sobrevive as peneiras; essa razao, nao.

Uso:
    .venv\\Scripts\\python.exe analisar_xp.py --base 16.7 --job 88.3
"""

from __future__ import annotations

import argparse
import pickle

import numpy as np

import memoria
from scan_xp import ESTADO, Bloco  # noqa: F401  (Bloco e preciso pro pickle)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--processo", default="SpiritVale")
    p.add_argument("--base", type=float, required=True,
                   help="porcentagem da barra base agora (ex.: 16.7)")
    p.add_argument("--job", type=float, required=True,
                   help="porcentagem da barra de job agora (ex.: 88.3)")
    p.add_argument("--tolerancia", type=float, default=0.25,
                   help="folga em pontos percentuais")
    p.add_argument("--folga", type=int, default=1024,
                   help="quantos bytes olhar em volta procurando o par")
    args = p.parse_args()

    with ESTADO.open("rb") as arquivo:
        blocos, meta = pickle.load(arquivo)

    alvos = {"base": args.base / 100, "job": args.job / 100}
    tol = args.tolerancia / 100

    pid = memoria.achar_processo(args.processo)
    if not pid:
        raise SystemExit(f"{args.processo} nao esta aberto.")

    achados = []
    with memoria.Processo(pid) as proc:
        for bloco in blocos:
            vivos = np.flatnonzero(bloco.vivos)
            if not len(vivos):
                continue
            inicio = bloco.inicio - args.folga
            dados = proc.ler(inicio, bloco.tamanho + args.folga * 2)
            if not dados:
                continue
            valores = np.frombuffer(dados, dtype="<i4",
                                    count=len(dados) // 4).astype(np.int64)
            desloc = args.folga // 4
            for i in vivos:
                indice = int(i) + desloc
                if not (0 <= indice < len(valores)):
                    continue
                atual = int(valores[indice])
                if atual <= 0:
                    continue
                # o "necessario" e sempre maior que o "atual"
                maiores = np.flatnonzero(valores > atual)
                for j in maiores:
                    necessario = int(valores[j])
                    razao = atual / necessario
                    for nome, alvo in alvos.items():
                        if abs(razao - alvo) <= tol:
                            achados.append({
                                "qual": nome, "razao": razao,
                                "end_atual": inicio + indice * 4, "atual": atual,
                                "end_nec": inicio + int(j) * 4,
                                "necessario": necessario,
                            })

    # o mesmo par aparece espelhado varias vezes; conta quantas
    grupos: dict[tuple, dict] = {}
    for a in achados:
        chave = (a["qual"], a["atual"], a["necessario"])
        grupo = grupos.setdefault(chave, {**a, "copias": 0, "enderecos": []})
        grupo["copias"] += 1
        grupo["enderecos"].append(a["end_atual"])

    if not grupos:
        print("Nenhum par bate com a porcentagem. Tente aumentar --tolerancia")
        print("ou --folga, ou faca mais uma rodada de subiu/parado.")
        return

    print(f"{len(grupos)} par(es) com a razao da barra:\n")
    for grupo in sorted(grupos.values(), key=lambda g: -g["copias"]):
        print(f"  [{grupo['qual']}] {grupo['atual']:,} / {grupo['necessario']:,}"
              f" = {grupo['razao'] * 100:.2f}%   "
              f"({grupo['copias']} copia(s) na memoria)")
        print(f"       atual em 0x{grupo['end_atual']:X}, "
              f"necessario em 0x{grupo['end_nec']:X} "
              f"({grupo['end_nec'] - grupo['end_atual']:+} bytes)")


if __name__ == "__main__":
    main()
