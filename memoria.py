"""Leitura da memoria do processo do jogo — SOMENTE LEITURA.

O handle e aberto com PROCESS_VM_READ e PROCESS_QUERY_INFORMATION apenas.
Nada aqui escreve na memoria do jogo, de proposito: o objetivo e ler valores
que a tela ja mostra (XP), sem a incerteza do OCR.

Por que isso existe: a barra de XP do jogo e translucida. Um nome de jogador
passando atras dela e texto branco na MESMA fonte — o OCR nao tem como separar
"2DWizard" do numero da barra. Memoria nao tem esse problema.

O jogo e Unity/IL2CPP (GameAssembly.dll), entao os enderecos mudam a cada
abertura por causa do ASLR. Por isso um endereco cru nao serve: o que se guarda
e uma CADEIA DE PONTEIROS ancorada na base de um modulo.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as w
import struct

k32 = ctypes.WinDLL("kernel32", use_last_error=True)

PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010
ACESSO_LEITURA = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ

TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010

MEM_COMMIT = 0x1000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
# paginas em que faz sentido procurar dado do jogo
LEGIVEIS = (0x02, 0x04, 0x20, 0x40)  # READONLY, READWRITE, EXECUTE_READ, EXECUTE_RW


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD),
                ("th32ProcessID", w.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", w.DWORD), ("szExeFile", w.WCHAR * 260)]


class MODULEENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", w.DWORD), ("th32ModuleID", w.DWORD),
                ("th32ProcessID", w.DWORD), ("GlblcntUsage", w.DWORD),
                ("ProccntUsage", w.DWORD), ("modBaseAddr", ctypes.POINTER(ctypes.c_byte)),
                ("modBaseSize", w.DWORD), ("hModule", w.HMODULE),
                ("szModule", w.WCHAR * 256), ("szExePath", w.WCHAR * 260)]


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [("BaseAddress", ctypes.c_ulonglong),
                ("AllocationBase", ctypes.c_ulonglong),
                ("AllocationProtect", w.DWORD), ("__alignment1", w.DWORD),
                ("RegionSize", ctypes.c_ulonglong), ("State", w.DWORD),
                ("Protect", w.DWORD), ("Type", w.DWORD), ("__alignment2", w.DWORD)]


def achar_processo(nome: str) -> int | None:
    """PID do primeiro processo com esse nome (sem .exe tambem serve)."""
    alvo = nome.lower().removesuffix(".exe")
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return None
    try:
        entrada = PROCESSENTRY32W()
        entrada.dwSize = ctypes.sizeof(entrada)
        if not k32.Process32FirstW(snap, ctypes.byref(entrada)):
            return None
        while True:
            if entrada.szExeFile.lower().removesuffix(".exe") == alvo:
                return entrada.th32ProcessID
            if not k32.Process32NextW(snap, ctypes.byref(entrada)):
                return None
    finally:
        k32.CloseHandle(snap)


def modulos(pid: int) -> dict[str, tuple[int, int]]:
    """{nome do modulo: (endereco base, tamanho)} — a ancora contra o ASLR."""
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == -1:
        return {}
    achados: dict[str, tuple[int, int]] = {}
    try:
        entrada = MODULEENTRY32W()
        entrada.dwSize = ctypes.sizeof(entrada)
        if not k32.Module32FirstW(snap, ctypes.byref(entrada)):
            return achados
        while True:
            base = ctypes.cast(entrada.modBaseAddr, ctypes.c_void_p).value or 0
            achados[entrada.szModule] = (base, entrada.modBaseSize)
            if not k32.Module32NextW(snap, ctypes.byref(entrada)):
                return achados
    finally:
        k32.CloseHandle(snap)


class Processo:
    """Handle de leitura. Use como context manager pra nao vazar o handle."""

    def __init__(self, pid: int):
        self.pid = pid
        self.handle = k32.OpenProcess(ACESSO_LEITURA, False, pid)
        if not self.handle:
            erro = ctypes.get_last_error()
            dica = ("\nRode o programa como administrador se o jogo tiver "
                    "privilegio maior." if erro == 5 else "")
            raise OSError(f"nao consegui abrir o processo {pid} (erro {erro}){dica}")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.fechar()

    def fechar(self) -> None:
        if self.handle:
            k32.CloseHandle(self.handle)
            self.handle = None

    # -- leitura ---------------------------------------------------------

    def ler(self, endereco: int, tamanho: int) -> bytes | None:
        buffer = (ctypes.c_char * tamanho)()
        lidos = ctypes.c_size_t(0)
        ok = k32.ReadProcessMemory(self.handle, ctypes.c_void_p(endereco),
                                   buffer, ctypes.c_size_t(tamanho),
                                   ctypes.byref(lidos))
        if not ok or lidos.value != tamanho:
            return None
        return bytes(buffer)

    def ler_int(self, endereco: int, tamanho: int = 4,
                sinal: bool = True) -> int | None:
        dados = self.ler(endereco, tamanho)
        if dados is None:
            return None
        return int.from_bytes(dados, "little", signed=sinal)

    def ler_float(self, endereco: int) -> float | None:
        dados = self.ler(endereco, 4)
        return struct.unpack("<f", dados)[0] if dados else None

    def ler_ponteiro(self, endereco: int) -> int | None:
        return self.ler_int(endereco, 8, sinal=False)

    # -- regioes ---------------------------------------------------------

    def regioes(self, minimo: int = 4096,
                maximo: int = 512 * 1024 * 1024) -> list[tuple[int, int]]:
        """Blocos de memoria comprometidos e legiveis, como (endereco, tamanho).

        Pula guard pages (ler uma dispara excecao no jogo) e blocos gigantes,
        que costumam ser textura/audio e nunca guardam um contador de XP.
        """
        info = MEMORY_BASIC_INFORMATION64()
        endereco = 0
        limite = 0x7FFFFFFFFFFF
        saida = []
        while endereco < limite:
            tamanho = k32.VirtualQueryEx(self.handle, ctypes.c_void_p(endereco),
                                         ctypes.byref(info), ctypes.sizeof(info))
            if not tamanho:
                break
            base, extensao = info.BaseAddress, info.RegionSize
            if (info.State == MEM_COMMIT
                    and info.Protect in LEGIVEIS
                    and not (info.Protect & PAGE_GUARD)
                    and minimo <= extensao <= maximo):
                saida.append((base, extensao))
            proximo = base + extensao
            if proximo <= endereco:
                break
            endereco = proximo
        return saida

    # -- cadeia de ponteiros ---------------------------------------------

    def resolver(self, modulo: str, deslocamentos: list[int]) -> int | None:
        """Segue base-do-modulo + offsets ate o endereco final.

        O primeiro deslocamento e somado a base do modulo; cada um seguinte e
        somado DEPOIS de dereferenciar. E assim que o endereco sobrevive ao
        ASLR: a base muda a cada abertura, os deslocamentos nao.
        """
        mods = modulos(self.pid)
        if modulo not in mods:
            return None
        endereco = mods[modulo][0] + deslocamentos[0]
        for passo in deslocamentos[1:]:
            ponteiro = self.ler_ponteiro(endereco)
            if not ponteiro:
                return None
            endereco = ponteiro + passo
        return endereco
