"""Acha uma CADEIA DE PONTEIROS ate um endereco — pra ele sobreviver ao ASLR.

O endereco cru de um valor muda toda vez que o jogo abre. O que nao muda e o
caminho ate ele: um deslocamento fixo dentro de um modulo (GameAssembly.dll),
que aponta pra um objeto, que aponta pra outro, ate o valor.

Busca de tras pra frente: quem contem um ponteiro que cai em cima do alvo?
E quem aponta pra esse? Cada nivel e uma varredura completa da memoria, e a
busca para quando um dos ponteiros esta DENTRO de um modulo — ali o endereco
e estavel, porque so depende de onde o Windows carregou a DLL.

Uso:
    .venv\\Scripts\\python.exe ponteiro_xp.py --alvo 0x271E8E18400 --niveis 4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

import memoria
from scan_xp import abrir_jogo, regioes_de_dados

SAIDA = Path(__file__).resolve().parent / "debug" / "cadeia_xp.json"


def quem_aponta(proc, regioes, alvos: np.ndarray, folga: int) -> list[tuple[int, int, int]]:
    """(endereco do ponteiro, alvo que ele alcanca, deslocamento)."""
    alvos = np.sort(alvos)
    achados = []
    for inicio, tamanho in regioes:
        dados = proc.ler(inicio, tamanho)
        if not dados:
            continue
        valores = np.frombuffer(dados, dtype="<u8", count=len(dados) // 8)
        # pra cada valor, o maior alvo que nao passa dele
        indice = np.searchsorted(alvos, valores, side="right") - 1
        ok = indice >= 0
        if not ok.any():
            continue
        idx = np.flatnonzero(ok)
        base = alvos[indice[idx]]
        delta = valores[idx].astype(np.int64) - base.astype(np.int64)
        bons = idx[(delta >= 0) & (delta <= folga)]
        for k in bons:
            valor = int(valores[k])
            alvo = int(alvos[np.searchsorted(alvos, valor, side="right") - 1])
            achados.append((inicio + int(k) * 8, alvo, valor - alvo))
    return achados


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--processo", default="SpiritVale")
    p.add_argument("--alvo", required=True, help="endereco final, em hex")
    p.add_argument("--niveis", type=int, default=4)
    p.add_argument("--folga", type=int, default=0x600,
                   help="maior deslocamento aceito dentro de um objeto")
    p.add_argument("--teto", type=int, default=40000,
                   help="maximo de ponteiros carregados por nivel")
    args = p.parse_args()
    alvo_final = int(args.alvo, 16)

    with abrir_jogo(args.processo) as proc:
        mods = memoria.modulos(proc.pid)
        faixas = {nome: (base, base + tam) for nome, (base, tam) in mods.items()
                  if tam > 0}
        regioes = regioes_de_dados(proc)
        # os modulos tambem precisam ser varridos: e neles que mora a ancora
        for nome, (base, tam) in mods.items():
            if tam > 4096:
                regioes.append((base, min(tam, 64 * 1024 * 1024)))

        # cada nivel: {endereco do ponteiro: (alvo alcancado, deslocamento)}
        atual = {alvo_final: None}
        caminho: list[dict] = []
        for nivel in range(1, args.niveis + 1):
            alvos = np.array(sorted(atual), dtype=np.uint64)
            achados = quem_aponta(proc, regioes, alvos, args.folga)
            print(f"nivel {nivel}: {len(achados):,} ponteiro(s) apontando pra "
                  f"{len(alvos):,} alvo(s)")
            if not achados:
                print("  ninguem aponta pra ca — tente aumentar --folga")
                break

            # ancora: algum desses ponteiros esta DENTRO de um modulo?
            ancoras = []
            for endereco, alvo, desloc in achados:
                for nome, (ini, fim) in faixas.items():
                    if ini <= endereco < fim:
                        ancoras.append((nome, endereco - ini, endereco, alvo, desloc))
                        break
            if ancoras:
                print(f"\n  {len(ancoras)} ancora(s) DENTRO de modulo:")
                for nome, rel, endereco, alvo, desloc in ancoras[:10]:
                    print(f"    {nome}+0x{rel:X}  ->  0x{alvo:X} (+0x{desloc:X})")
                caminho.append({"nivel": nivel, "ancoras": [
                    {"modulo": n, "offset": r, "desloc": d}
                    for n, r, _e, _a, d in ancoras[:10]]})
                SAIDA.parent.mkdir(parents=True, exist_ok=True)
                SAIDA.write_text(json.dumps(
                    {"alvo": hex(alvo_final), "niveis": caminho}, indent=2),
                    encoding="utf-8")
                print(f"\n  gravado em {SAIDA.name}")
                return

            novos = {}
            for endereco, alvo, desloc in achados[:args.teto]:
                novos[endereco] = (alvo, desloc)
            atual = novos
            caminho.append({"nivel": nivel, "quantos": len(achados)})

        print("\nNao cheguei num modulo. Aumente --niveis ou --folga.")


if __name__ == "__main__":
    main()
