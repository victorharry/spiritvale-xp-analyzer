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
    # Pede elevacao no manifesto: o Windows mostra a UAC ao abrir e o programa
    # nunca roda sem ela. Sem isso, ler a rede so funciona com o Npcap
    # instalado — e quem nao tinha via a janela vazia sem entender por que.
    #
    # A UAC toda vez incomoda, mas incomoda de um jeito PREVISIVEL: o usuario
    # clica em Sim e funciona. A alternativa era um programa que as vezes
    # funciona e as vezes nao, dependendo de um componente que ele nem sabe
    # que existe.
    #
    # Com o Npcap instalado o caminho dele continua sendo o preferido (ver
    # captura.abrir_captura); a elevacao so garante que HA um caminho.
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
