"""Coisas pequenas que o app inteiro usa: config, DPI e console.

Era um modulo grande, herdado da automacao de mercado: OCR, captura de tela,
agrupamento de palavras, dezenas de opcoes de calibracao. Nada disso e chamado
desde que o XP passou a vir da rede, e cada dependencia a mais e peso no
instalador e mais uma chance do antivirus reclamar — o que ja aconteceu de
verdade na maquina de um colega. Sobrou o que o XP Analyzer realmente usa.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CAMINHO_CONFIG = RAIZ / "config.json"

CONFIG_PADRAO = {
    # o processo do jogo, usado pra descobrir de quem sao as portas UDP
    "processo_jogo": "SpiritVale.exe",
    "xp_escala": 1.0,            # zoom da janelinha
    "xp_overlay_pos": None,      # [x, y] de onde ela ficou na ultima vez
    "xp_janela_minutos": 15,     # janela do ritmo medio
    # quanto XP cada nivel pede, medido (nao chutado). Chaves "base:114",
    # "job:16" — ver _aprender_no_level_up e registrar_amostra
    "xp_necessario": {},
}


def preparar_console() -> None:
    """Evita UnicodeEncodeError quando a saida e redirecionada para arquivo."""
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def ativar_dpi() -> None:
    """Faz o processo enxergar pixels fisicos.

    Sem isso, com escala do Windows diferente de 100%, a janelinha sai do
    tamanho errado e com o texto cortado.
    """
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor v2
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def carregar_config() -> dict:
    cfg = dict(CONFIG_PADRAO)
    if CAMINHO_CONFIG.exists():
        try:
            cfg.update(json.loads(CAMINHO_CONFIG.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            pass          # config corrompido nao impede o programa de abrir
    return cfg


def salvar_config(cfg: dict) -> None:
    CAMINHO_CONFIG.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
