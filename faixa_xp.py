"""Busca diferencial numa FAIXA de valores — sem depender de ancora.

A busca por ancora (nivel base perto do nivel de job) achou um objeto que
tinha a razao certa mas estava CONGELADO: uma copia velha, que nao acompanha
o jogo. Aqui a logica e outra e mais direta:

    guarda todo valor dentro de uma faixa plausivel de XP
    -> voce mata algo
    -> mantem so os que cresceram
    -> repete ate sobrar um

Nao assume onde o valor mora nem quem esta ao lado dele. So exige que se
comporte como XP: sobe quando voce ganha, fica parado quando voce nao ganha.

    faixa_xp.py iniciar --de 2900000 --ate 3100000
    faixa_xp.py subiu       (depois de matar algo)
    faixa_xp.py parado      (depois de ficar quieto)
    faixa_xp.py mostrar
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np

import memoria
from scan_xp import abrir_jogo, regioes_de_dados

ESTADO = Path(__file__).resolve().parent / "debug" / "faixa_xp.pkl"


def coletar(proc, de: int, ate: int) -> tuple[np.ndarray, np.ndarray]:
    """(enderecos, valores) de tudo que esta na faixa."""
    enderecos, valores = [], []
    for inicio, tamanho in regioes_de_dados(proc):
        dados = proc.ler(inicio, tamanho)
        if not dados:
            continue
        bloco = np.frombuffer(dados, dtype="<i4", count=len(dados) // 4)
        (achados,) = np.where((bloco >= de) & (bloco <= ate))
        if len(achados):
            enderecos.append(inicio + achados.astype(np.int64) * 4)
            valores.append(bloco[achados])
    if not enderecos:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int32)
    return np.concatenate(enderecos), np.concatenate(valores)


def reler(proc, enderecos: np.ndarray) -> np.ndarray:
    """Le de novo cada endereco guardado (agrupando por pagina, pra ser rapido)."""
    atuais = np.zeros(len(enderecos), dtype=np.int64)
    ordem = np.argsort(enderecos)
    i = 0
    while i < len(ordem):
        base = int(enderecos[ordem[i]]) & ~0xFFF
        mesmo = []
        while i < len(ordem) and (int(enderecos[ordem[i]]) & ~0xFFF) == base:
            mesmo.append(ordem[i])
            i += 1
        pagina = proc.ler(base, 4096)
        if pagina is None:
            for k in mesmo:
                atuais[k] = np.iinfo(np.int64).min   # marca como perdido
            continue
        vetor = np.frombuffer(pagina, dtype="<i4", count=1024)
        for k in mesmo:
            atuais[k] = int(vetor[(int(enderecos[k]) - base) // 4])
    return atuais


def salvar(enderecos, valores, passadas):
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    with ESTADO.open("wb") as arquivo:
        pickle.dump((enderecos, valores, passadas), arquivo)


def carregar():
    if not ESTADO.exists():
        raise SystemExit("Nada em andamento. Rode: faixa_xp.py iniciar --de N --ate M")
    with ESTADO.open("rb") as arquivo:
        return pickle.load(arquivo)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("acao", choices=["iniciar", "subiu", "parado", "mostrar"])
    p.add_argument("--processo", default="SpiritVale")
    p.add_argument("--de", type=int, default=1)
    p.add_argument("--ate", type=int, default=2_000_000_000)
    p.add_argument("--max-delta", type=int, default=1_000_000,
                   help="maior crescimento aceitavel numa passada")
    args = p.parse_args()

    with abrir_jogo(args.processo) as proc:
        if args.acao == "iniciar":
            enderecos, valores = coletar(proc, args.de, args.ate)
            salvar(enderecos, valores, [])
            print(f"{len(enderecos):,} valores entre {args.de:,} e {args.ate:,}")
            print("\nAgora GANHE XP e rode:  faixa_xp.py subiu")
            return

        enderecos, valores, passadas = carregar()
        if args.acao == "mostrar":
            atuais = reler(proc, enderecos)
            print(f"passadas: {' -> '.join(passadas) or '(nenhuma)'}")
            print(f"{len(enderecos)} candidato(s):\n")
            for endereco, valor in zip(enderecos[:60], atuais[:60]):
                print(f"  0x{int(endereco):X}   {int(valor):>13,}")
            if len(enderecos) > 60:
                print(f"  ... e mais {len(enderecos) - 60}")
            return

        atuais = reler(proc, enderecos)
        if args.acao == "subiu":
            delta = atuais - valores.astype(np.int64)
            ok = (delta > 0) & (delta <= args.max_delta)
        else:
            ok = atuais == valores.astype(np.int64)
        enderecos, valores = enderecos[ok], atuais[ok].astype(np.int32)
        passadas.append(args.acao)
        salvar(enderecos, valores, passadas)
        print(f"passada '{args.acao}': {len(ok):,} -> {len(enderecos):,}")
        if len(enderecos) <= 40:
            print("\nJa da pra olhar:  faixa_xp.py mostrar")
        else:
            outra = "parado" if args.acao == "subiu" else "subiu"
            print(f"\nAgora {'fique quieto' if outra == 'parado' else 'ganhe XP'}"
                  f" e rode:  faixa_xp.py {outra}")


if __name__ == "__main__":
    main()
