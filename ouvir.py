"""Ferramenta de linha de comando pra ver a captura funcionando.

    .venv\\Scripts\\python.exe ouvir.py

Mostra o nivel e o XP absoluto do personagem conforme os pacotes chegam. Serve
pra confirmar que o Npcap esta instalado, que a placa certa foi escolhida e que
o jogo esta sendo visto — antes de mexer no XP Analyzer.

Se nada aparecer, o proprio programa lista o que checar, na ordem em que
costuma falhar.
"""

from __future__ import annotations

import sys
import time

import captura


def main() -> int:
    print("XP Analyzer — escuta de rede\n")
    for linha in captura.diagnostico():
        print("  " + linha)
    print()

    monitor = captura.Monitor(ao_avisar=lambda t: print(f"  [captura] {t}"))
    monitor.iniciar()
    print("  ganhe XP no jogo. Ctrl+C encerra.\n")

    anterior = None
    ultimo_estado = ""
    try:
        while monitor.ativo:
            time.sleep(0.3)
            if monitor.estado != ultimo_estado:
                ultimo_estado = monitor.estado
                print(f"  [estado] {ultimo_estado}")
            atual = monitor.ultimo
            if atual is None or atual == anterior:
                continue
            ganho = ""
            if anterior is not None and anterior.nome == atual.nome:
                delta = atual.xp - anterior.xp
                delta_job = atual.xp_job - anterior.xp_job
                if delta or delta_job:
                    ganho = f"   (+{delta} classe, +{delta_job} job)"
            print(f"  {atual.nome}  |  classe {atual.nivel} — {atual.xp:,} XP"
                  f"  |  job {atual.nivel_job} — {atual.xp_job:,} XP{ganho}")
            anterior = atual
    except KeyboardInterrupt:
        print("\n  encerrando...")
    finally:
        monitor.parar()

    if monitor.ultimo is None:
        print("\n  Nenhum personagem lido.")
        print("  - a captura precisa de UMA das duas: Npcap instalado")
        print("    (https://npcap.com/#download, com 'WinPcap API-compatible")
        print("    Mode' MARCADO), ou rodar este programa como administrador")
        print("  - o jogo precisa estar aberto e conectado a um servidor")
        print(f"  - pacotes do jogo vistos ate agora: {monitor.pacotes}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
