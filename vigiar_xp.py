"""Acompanha ao vivo um par (XP atual, XP do nivel) na memoria do jogo.

E a prova final: a porcentagem calculada aqui tem que bater com a barra, e
andar junto com ela quando voce mata alguma coisa.

Uso:
    .venv\\Scripts\\python.exe vigiar_xp.py --atual 0x2734AE56738 --nec 0x2734AE562E8
"""

from __future__ import annotations

import argparse
import time

import memoria


def endereco(texto: str) -> int:
    return int(texto, 16) if texto.lower().startswith("0x") else int(texto)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--processo", default="SpiritVale")
    p.add_argument("--atual", type=endereco, required=True)
    p.add_argument("--nec", type=endereco, required=True)
    p.add_argument("--segundos", type=float, default=60)
    p.add_argument("--intervalo", type=float, default=1.0)
    args = p.parse_args()

    pid = memoria.achar_processo(args.processo)
    if not pid:
        raise SystemExit(f"{args.processo} nao esta aberto.")

    fim = time.time() + args.segundos
    anterior = None
    print(f"{'hora':<9} {'XP atual':>14} {'XP do nivel':>14} {'%':>8}   variacao")
    with memoria.Processo(pid) as proc:
        while time.time() < fim:
            atual = proc.ler_int(args.atual)
            necessario = proc.ler_int(args.nec)
            if atual is None or necessario is None:
                print("  leitura falhou (o endereco pode ter sido liberado)")
                break
            pct = atual / necessario * 100 if necessario else 0
            variacao = "" if anterior is None else f"{atual - anterior:+,}"
            if anterior is None or atual != anterior:
                print(f"{time.strftime('%H:%M:%S'):<9} {atual:>14,} "
                      f"{necessario:>14,} {pct:>7.2f}%   {variacao}")
            anterior = atual
            time.sleep(args.intervalo)
    print("\nSe a % acima bate com a barra do jogo e andou junto quando voce")
    print("matou algo, achamos o campo.")


if __name__ == "__main__":
    main()
