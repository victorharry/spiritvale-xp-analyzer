r"""Checks that the packaged build came out whole, before it becomes an installer.

    .venv\Scripts\python.exe verify_build.py

This exists because the failure slipped through twice, and it slips through in
the worst way: with the XP Analyzer running, PyInstaller cannot replace the
DLLs, prints the error in the middle of hundreds of log lines, and **exits with
status zero**. Inno Setup then packages a half-built folder without complaining
about anything, and Setup.exe quietly shrinks from 11 MB to 8.6.

Size is the most reliable signal of wholeness here: a complete package is tens
of megabytes across hundreds of files. If anything is missing, both drop.
"""

from __future__ import annotations

import sys
from pathlib import Path

FOLDER = Path(__file__).resolve().parent / "dist" / "XP Analyzer"
EXECUTABLE = FOLDER / "XP Analyzer.exe"

# measured on a healthy package (~29 MB, ~960 files). The slack is generous on
# purpose, so this only fires when something is genuinely missing.
MIN_SIZE = 24 * 1024 * 1024
MIN_FILES = 60

# without these the program opens and dies, and the failure shows up only on
# somebody else's machine
ESSENTIAL = ("_internal/libffi-8.dll", "_internal/base_library.zip",
             "_internal/customtkinter", "_internal/_socket.pyd")


def problems() -> list[str]:
    if not EXECUTABLE.exists():
        return [f"missing: {EXECUTABLE}"]

    found = []
    files = [f for f in FOLDER.rglob("*") if f.is_file()]
    size = sum(f.stat().st_size for f in files)
    if size < MIN_SIZE:
        found.append(f"package too small: {size / 1e6:.1f} MB "
                     f"(expected at least {MIN_SIZE / 1e6:.0f} MB)")
    if len(files) < MIN_FILES:
        found.append(f"too few files: {len(files)} "
                     f"(expected at least {MIN_FILES})")
    for relative in ESSENTIAL:
        if not (FOLDER / relative).exists():
            found.append(f"missing: {relative}")
    return found


def main() -> int:
    found = problems()
    if found:
        print("INCOMPLETE BUILD — do not build the installer from this:\n")
        for line in found:
            print(f"  - {line}")
        print("\nAlmost always the XP Analyzer is open and holding the DLLs.")
        print("Close the program and run Build.bat again.")
        return 1

    files = [f for f in FOLDER.rglob("*") if f.is_file()]
    size = sum(f.stat().st_size for f in files)
    print(f"package OK: {size / 1e6:.1f} MB across {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
