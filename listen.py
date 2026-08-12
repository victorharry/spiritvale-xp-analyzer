"""Ferramenta de linha de comando pra ver a capture funcionando.

    .venv\\Scripts\\python.exe ouvir.py

Mostra o level e o XP absoluto do character conforme os packets chegam. Serve
pra confirmar que o Npcap esta instalado, que a placa certa foi escolhida e que
o jogo esta sendo visto — antes de mexer no XP Analyzer.

Se nada aparecer, o proprio program list_of o que checar, na ordem em que
costuma falhar.
"""

from __future__ import annotations

import sys
import time

import capture


def main() -> int:
    print("XP Analyzer — escuta de rede\n")
    for linha in capture.diagnose():
        print("  " + linha)
    print()

    monitor = capture.Monitor(ao_avisar=lambda t: print(f"  [capture] {t}"))
    monitor.start()
    print("  ganhe XP no jogo. Ctrl+C encerra.\n")

    anterior = None
    ultimo_estado = ""
    try:
        while monitor.running:
            time.sleep(0.3)
            if monitor.state != ultimo_estado:
                ultimo_estado = monitor.state
                print(f"  [state] {ultimo_estado}")
            current = monitor.latest
            if current is None or current == anterior:
                continue
            ganho = ""
            if anterior is not None and anterior.name == current.name:
                delta = current.xp - anterior.xp
                delta_job = current.job_xp - anterior.job_xp
                if delta or delta_job:
                    ganho = f"   (+{delta} classe, +{delta_job} job)"
            print(f"  {current.name}  |  classe {current.level} — {current.xp:,} XP"
                  f"  |  job {current.job_level} — {current.job_xp:,} XP{ganho}")
            anterior = current
    except KeyboardInterrupt:
        print("\n  encerrando...")
    finally:
        monitor.stop()

    if monitor.latest is None:
        print("\n  Nenhum character lido.")
        print("  - a capture precisa de UMA das duas: Npcap instalado")
        print("    (https://npcap.com/#download, com 'WinPcap API-compatible")
        print("    Mode' MARCADO), ou rodar este program como administrador")
        print("  - o jogo precisa estar aberto e conectado a um servidor")
        print(f"  - packets do jogo vistos ate agora: {monitor.packets}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
