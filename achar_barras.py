"""Reencontra as barras de XP na memoria a cada abertura do jogo.

A cadeia de ponteiros classica nao ancorou: em Unity/IL2CPP os objetos vivem
no heap gerenciado e os campos estaticos nao ficam dentro da imagem da DLL,
entao nao existe "GameAssembly.dll + offset fixo" pra este valor.

A saida e outra: o que achamos e o `fillAmount` de uma barra de UI (por isso
tem COR em volta — 0.96078 e 245/255, 0.78431 e 200/255). Esse componente tem
um formato reconhecivel, e as duas barras sao instancias vizinhas, separadas
por um passo fixo. Da pra reencontra-lo por ASSINATURA em poucos segundos, sem
depender de endereco fixo.

A confirmacao final e cruzada: a leitura da memoria tem que bater com o que o
OCR ve na tela. O OCR so precisa acertar UMA vez, grosseiramente, pra desempatar
— dai em diante quem manda e a memoria, que e exata.
"""

from __future__ import annotations

import argparse

import numpy as np

import memoria
from scan_xp import abrir_jogo, regioes_de_dados

# cores encontradas em volta do fillAmount, em deslocamentos fixos
ASSINATURA = ((180, 0.960784), (196, 0.784314), (240, 0.501961), (248, 0.10))
PASSO_BARRAS = 368   # distancia entre a barra de job e a de base
TOL_COR = 0.0005


def achar_barras(proc) -> list[dict]:
    """Pares (job, base) que tem a assinatura de barra de XP."""
    achados = []
    maior = max(desloc for desloc, _ in ASSINATURA)
    for inicio, tamanho in regioes_de_dados(proc):
        dados = proc.ler(inicio, tamanho)
        if not dados:
            continue
        n = len(dados) // 4
        vetor = np.frombuffer(dados, dtype="<f4", count=n)
        with np.errstate(invalid="ignore"):
            # candidato: float entre 0 e 1 (o preenchimento da barra)
            possivel = (vetor >= 0.0) & (vetor <= 1.0)
            limite = n - (maior + PASSO_BARRAS) // 4 - 1
            possivel[limite:] = False
            for desloc, cor in ASSINATURA:
                passo = desloc // 4
                deslocado = np.empty(n, dtype=bool)
                deslocado[:n - passo] = np.abs(
                    vetor[passo:] - cor) < TOL_COR
                deslocado[n - passo:] = False
                possivel &= deslocado
        for i in np.flatnonzero(possivel):
            endereco = inicio + int(i) * 4
            outro = proc.ler_float(endereco + PASSO_BARRAS)
            if outro is None or not (0.0 <= outro <= 1.0):
                continue
            achados.append({"job": endereco, "job_pct": float(vetor[i]) * 100,
                            "base": endereco + PASSO_BARRAS,
                            "base_pct": outro * 100})
    return achados


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--processo", default="SpiritVale")
    p.add_argument("--base", type=float,
                   help="%% da barra base agora, pra confirmar (opcional)")
    p.add_argument("--job", type=float,
                   help="%% da barra de job agora, pra confirmar (opcional)")
    p.add_argument("--tolerancia", type=float, default=3.0,
                   help="folga em pontos percentuais na confirmacao")
    args = p.parse_args()

    with abrir_jogo(args.processo) as proc:
        achados = achar_barras(proc)
    print(f"{len(achados)} par(es) com a assinatura de barra de XP\n")

    if args.base is not None and args.job is not None:
        bons = [a for a in achados
                if abs(a["base_pct"] - args.base) <= args.tolerancia
                and abs(a["job_pct"] - args.job) <= args.tolerancia]
        print(f"{len(bons)} bate(m) com a tela (base {args.base}%, "
              f"job {args.job}%):")
        achados = bons or achados

    for a in achados[:15]:
        print(f"  job 0x{a['job']:X} = {a['job_pct']:6.2f}%   "
              f"base 0x{a['base']:X} = {a['base_pct']:6.2f}%")


if __name__ == "__main__":
    main()
