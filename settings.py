"""Small things the whole app needs: settings, DPI and console.

This used to be a large module full of things this program no longer does.
None of it was called once XP started coming from the network, and every extra
dependency is weight in the installer and one more chance for antivirus to
complain — which has already happened on a friend's machine. What is left is
what the XP Analyzer actually uses.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path

# Frozen into an .exe, __file__ points at a temporary folder that vanishes
# on exit. Without this detour, everything the app learned — the window
# position, any measurements — would be lost on every run, and the user would
# never understand why it "forgets" things.
if getattr(sys, "frozen", False):
    ROOT = Path(os.environ.get("APPDATA") or Path.home()) / "XP Analyzer"
    ROOT.mkdir(parents=True, exist_ok=True)
else:
    ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    # the game process, used to find out which UDP ports belong to it
    "processo_jogo": "SpiritVale.exe",
    "xp_escala": 1.0,            # zoom da janelinha
    "xp_overlay_pos": None,      # [x, y] de onde ela ficou na ultima vez
    "xp_janela_minutos": 15,     # janela do ritmo medio
    # quanto XP cada level pede, medido (nao chutado). Chaves "base:114",
    # "job:16" — ver _aprender_no_level_up e registrar_amostra
    "xp_necessario": {},
    # every estimate collected per level; the value used is their median
    "xp_amostras": {},
    # ask GitHub for a newer release at startup (see updates.py)
    "update_check": True,
    # the version whose notice the user closed; it is not shown again
    "update_skipped": "",
}


def prepare_console() -> None:
    """Avoids UnicodeEncodeError when output is redirected to a file."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def enable_dpi_awareness() -> None:
    """Makes the process see physical pixels.

    Without this, at any Windows scale other than 100%, the overlay comes out
    wrong size with clipped text.
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


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            # a corrupt settings file must not stop the program from opening
            pass
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
