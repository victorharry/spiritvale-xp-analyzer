# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files

datas = []
datas += collect_data_files('customtkinter')


a = Analysis(
    ['xp_analyzer.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # o app so precisa de customtkinter. Excluir explicitamente evita que o
    # PyInstaller arraste pacotes pesados que estejam no venv por acaso —
    # instalador menor e menos motivo pro antivirus reclamar
    excludes=['matplotlib', 'pandas', 'pytesseract', 'PIL', 'numpy', 'mss',
              'pyautogui', 'scipy', 'cv2'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    # Asks for elevation in the manifest: Windows shows the UAC prompt on
    # launch and the program never runs without it. Without this, reading the
    # network only works when Npcap is installed — and whoever lacked it saw
    # an empty window with no idea why.
    #
    # A prompt every time is annoying, but it is annoying PREDICTABLY: you
    # click Yes and it works. The alternative was a program that sometimes
    # works and sometimes does not, depending on a component the user does
    # not know exists.
    #
    # With Npcap installed its path is still preferred (see
    # capture.open_capture_backend); elevation only guarantees a path exists.
    uac_admin=True,
    name='XP Analyzer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XP Analyzer',
)
