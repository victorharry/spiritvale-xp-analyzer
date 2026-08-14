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
    # show the gold block. On by default; the "$" button turns it off
    "mostrar_ouro": True,
    # ask GitHub for a newer release at startup (see updates.py)
    "update_check": True,
    # the version whose notice the user closed; it is not shown again
    "update_skipped": "",
}


# The installer looks for this name to find out the program is running (see
# AppMutex in installer.iss). Without it, installing over a running copy fails
# in the worst possible place: halfway through the file copy, on "DeleteFile
# failed; code 5", with the user left choosing between "Try again" and a
# half-updated install.
#
# The app runs elevated and the installer does not, so this is the only thing
# that can bridge them: the installer cannot close an elevated process, and
# Windows' Restart Manager cannot either. It can only ask the user to.
MUTEX_NAME = "XPAnalyzerRunning"
_mutexes: list[int] = []

# MUTEX_ALL_ACCESS to Everyone, and the width is deliberate.
#
# A mutex created by an elevated process gets a default DACL written for the
# elevated token, where the access goes to the Administrators group — a group
# that is marked deny-only in the token of the unelevated installer. It would
# be refused, find nothing, and fail on the locked DLL exactly as before.
#
# SYNCHRONIZE alone is not enough either, even though it is all OpenMutex
# needs. A second copy of the app detects the first by CREATING the mutex and
# being told the name was taken, and CreateMutex on an existing object asks for
# full access: with a narrower DACL it came back "access denied", the handle
# was null, and the second copy happily started alongside the first.
#
# Nothing is protected by this mutex. It carries one bit — "the app is open" —
# and is never waited on, so an open DACL costs nothing.
_SDDL = "D:(A;;0x1F0001;;;WD)"


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [("nLength", ctypes.c_ulong),
                ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", ctypes.c_int)]


def _open_to_everyone():
    """SECURITY_ATTRIBUTES from `_SDDL`, or None if it could not be built."""
    advapi = ctypes.windll.advapi32
    build = advapi.ConvertStringSecurityDescriptorToSecurityDescriptorW
    build.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong,
                      ctypes.POINTER(ctypes.c_void_p),
                      ctypes.POINTER(ctypes.c_ulong)]
    build.restype = ctypes.c_int
    descriptor = ctypes.c_void_p()
    if not build(_SDDL, 1, ctypes.byref(descriptor), None):   # 1 = SDDL rev. 1
        return None
    return _SecurityAttributes(ctypes.sizeof(_SecurityAttributes),
                               descriptor, False)


ERROR_ALREADY_EXISTS = 183


def announce_running() -> bool:
    """Publishes a named mutex that lives as long as this process does.

    Returns whether this is the FIRST copy running. Creating the mutex already
    answers that — Windows says whether the name was taken — so the same call
    covers both jobs.

    Two names on purpose. The `Global\\` one crosses sessions and elevation
    levels, which is the gap that matters for the installer; creating it needs
    a privilege a plain user may not have, so the session-local one is the
    fallback. The installer checks both and only needs one.

    The "am I the first" answer comes from the session-local name, never the
    global one: two people logged into the same machine are two separate
    desktops, each entitled to its own overlay.
    """
    if os.name != "nt":
        return True
    if _mutexes:
        return True                       # already announced, by us
    # NOT ctypes.windll.kernel32: on that handle the error code has to be read
    # with a second, separate call to GetLastError, and by then ctypes has made
    # calls of its own and the value is whatever they left behind. It reported
    # "the name was free" while another copy was holding it. With
    # use_last_error, ctypes captures the code at the call itself.
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                    ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p    # a HANDLE is pointer-sized
    try:
        attributes = _open_to_everyone()
    except Exception:
        attributes = None
    first = True
    for name in (f"Global\\{MUTEX_NAME}", MUTEX_NAME):
        try:
            handle = kernel.CreateMutexW(
                ctypes.byref(attributes) if attributes else None, False, name)
            taken = ctypes.get_last_error() == ERROR_ALREADY_EXISTS
        except Exception:
            continue
        if handle:
            # kept in a module global so it is never garbage collected: closing
            # the handle would tell the installer the program had quit
            _mutexes.append(handle)
        else:
            # could not create it at all — an older copy with a stricter DACL,
            # or no privilege for the Global namespace. Then the only question
            # left is whether the name exists, which needs far less access.
            taken = _exists(name)
        if name == MUTEX_NAME and taken:
            first = False
    return first


def _exists(name: str) -> bool:
    """Whether some other process already holds this mutex."""
    try:
        kernel = ctypes.windll.kernel32
        kernel.OpenMutexW.argtypes = [ctypes.c_ulong, ctypes.c_int,
                                      ctypes.c_wchar_p]
        kernel.OpenMutexW.restype = ctypes.c_void_p
        handle = kernel.OpenMutexW(0x00100000, False, name)   # SYNCHRONIZE
    except Exception:
        return False
    if not handle:
        return False
    ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(handle))
    return True


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
