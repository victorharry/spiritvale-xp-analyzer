"""Acha a porcentagem da barra guardada como float, pelo TAMANHO do passo.

Float perto de 0,917 tem aos milhares na memoria (cor, alfa, curva de
animacao). O que quase nenhum tem e andar exatamente o que a barra andou:
matar dois mobs move o job de 0,911 pra 0,917, e so o valor certo faz isso.

    float_xp.py foto --base 18.9 --job 91.7      (antes de matar)
    ... mate os mobs ...
    float_xp.py conferir --base 19.4 --job 92.3  (depois, com a barra nova)
"""

from __future__ import annotations

import argparse
import pickle
from pathlib import Path

import numpy as np

import memoria
from scan_xp import abrir_jogo, regioes_de_dados

ESTADO = Path(__file__).resolve().parent / "debug" / "float_xp.pkl"
TOL = 0.0008


def coletar(proc, alvos: dict[str, float]) -> dict[str, tuple]:
    saida = {nome: ([], []) for nome in alvos}
    for inicio, tamanho in regioes_de_dados(proc):
        dados = proc.ler(inicio, tamanho)
        if not dados:
            continue
        vetor = np.frombuffer(dados, dtype="<f4", count=len(dados) // 4)
        with np.errstate(invalid="ignore"):
            for nome, alvo in alvos.items():
                (achados,) = np.where(np.abs(vetor - alvo) < TOL)
                if len(achados):
                    saida[nome][0].append(inicio + achados.astype(np.int64) * 4)
                    saida[nome][1].append(vetor[achados])
    return {nome: (np.concatenate(e) if e else np.array([], dtype=np.int64),
                   np.concatenate(v) if v else np.array([], dtype=np.float32))
            for nome, (e, v) in saida.items()}


def reler(proc, enderecos: np.ndarray) -> np.ndarray:
    atuais = np.full(len(enderecos), np.nan, dtype=np.float64)
    for i, endereco in enumerate(enderecos):
        valor = proc.ler_float(int(endereco))
        if valor is not None:
            atuais[i] = valor
    return atuais


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("acao", choices=["foto", "conferir"])
    p.add_argument("--processo", default="SpiritVale")
    p.add_argument("--base", type=float, required=True)
    p.add_argument("--job", type=float, required=True)
    args = p.parse_args()
    alvos = {"base": args.base / 100, "job": args.job / 100}

    with abrir_jogo(args.processo) as proc:
        if args.acao == "foto":
            dados = coletar(proc, alvos)
            ESTADO.parent.mkdir(parents=True, exist_ok=True)
            with ESTADO.open("wb") as arquivo:
                pickle.dump((dados, alvos), arquivo)
            for nome, (enderecos, _) in dados.items():
                print(f"  {nome}: {len(enderecos):,} float(s) perto de "
                      f"{alvos[nome]:.4f}")
            print("\nAgora mate os mobs e rode 'conferir' com a barra nova.")
            return

        with ESTADO.open("rb") as arquivo:
            dados, antigos = pickle.load(arquivo)
        for nome, (enderecos, valores) in dados.items():
            if not len(enderecos):
                continue
            atuais = reler(proc, enderecos)
            esperado = alvos[nome]
            ok = np.abs(atuais - esperado) < TOL
            print(f"\n{nome}: {ok.sum()} de {len(enderecos):,} foram de "
                  f"{antigos[nome]:.4f} para {esperado:.4f}")
            for endereco, antes, agora in zip(enderecos[ok][:15],
                                              valores[ok][:15],
                                              atuais[ok][:15]):
                print(f"   0x{int(endereco):X}   {float(antes):.5f} -> {agora:.5f}")


if __name__ == "__main__":
    main()
