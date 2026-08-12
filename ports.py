"""Quais ports UDP pertencem ao processo do jogo.

Without this the capture would see every UDP packet on this machine —
Windows Update — e tentaria decode tudo como se fosse do jogo. Perguntar
came from the game. Asking Windows who owns each socket is the cheapest
and most honest filter there is: instead of guessing from the packet's

shape, we ask the owner. This calls iphlpapi directly rather than
shelling out to netstat.exe, which would flash a console window.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w

iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)

TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32W(ctypes.Structure):
    """Just enough to list processes and find the game's PID.

    This is process enumeration, not memory reading — nothing here opens a
    handle with PROCESS_VM_READ. It is inline on purpose: while a `memory`
    module was imported from here, the promise of "never reads the game's
    memory" depended on nobody calling what lived inside it. Now the capability
    does not exist in the project at all.
    """

    _fields_ = [("dwSize", w.DWORD), ("cntUsage", w.DWORD),
                ("th32ProcessID", w.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                ("th32ModuleID", w.DWORD), ("cntThreads", w.DWORD),
                ("th32ParentProcessID", w.DWORD), ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", w.DWORD), ("szExeFile", w.WCHAR * 260)]

AF_INET = 2
AF_INET6 = 23
UDP_TABLE_OWNER_PID = 1
ERROR_INSUFFICIENT_BUFFER = 122          # ERROR_INSUFFICIENT_BUFFER

ROW_SIZE_V4 = 12              # dwLocalAddr + dwLocalPort + dwOwningPid
ROW_SIZE_V6 = 28              # 16 de address + escopo + port + pid


def pids(name: str) -> set[int]:
    """Every process with that name (the game can have more than one window)."""
    alvo = name.lower().removesuffix(".exe")
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return set()
    found: set[int] = set()
    try:
        entrada = PROCESSENTRY32W()
        entrada.dwSize = ctypes.sizeof(entrada)
        if not k32.Process32FirstW(snap, ctypes.byref(entrada)):
            return found
        while True:
            if entrada.szExeFile.lower().removesuffix(".exe") == alvo:
                found.add(entrada.th32ProcessID)
            if not k32.Process32NextW(snap, ctypes.byref(entrada)):
                return found
    finally:
        k32.CloseHandle(snap)


def _udp_table(familia: int) -> bytes:
    size = w.DWORD(0)
    iphlpapi.GetExtendedUdpTable(None, ctypes.byref(size), False,
                                 familia, UDP_TABLE_OWNER_PID, 0)
    if size.value == 0:
        return b""
    buffer = ctypes.create_string_buffer(size.value)
    code = iphlpapi.GetExtendedUdpTable(buffer, ctypes.byref(size), False,
                                          familia, UDP_TABLE_OWNER_PID, 0)
    return buffer.raw if code == 0 else b""


def _port_number(raw_value: int) -> int:
    """The field arrives in network order, stored inside a full DWORD."""
    return ((raw_value & 0xFF) << 8) | ((raw_value >> 8) & 0xFF)


def _rows(data: bytes, row_size: int, port_offset: int):
    if len(data) < 4:
        return
    how_many = int.from_bytes(data[:4], "little")
    # the compiler aligns the first row; in both tables it starts at offset 4
    start = 4
    for i in range(how_many):
        base = start + i * row_size
        if base + row_size > len(data):
            return
        linha = data[base:base + row_size]
        port = _port_number(int.from_bytes(
            linha[port_offset:port_offset + 4], "little"))
        pid = int.from_bytes(linha[row_size - 4:row_size], "little")
        yield port, pid


def ports_of(processes: set[int]) -> set[int]:
    """Portas UDP locais abertas por esses PIDs."""
    if not processes:
        return set()
    found_ports: set[int] = set()
    for familia, size, desloc in ((AF_INET, ROW_SIZE_V4, 4),
                                     (AF_INET6, ROW_SIZE_V6, 20)):
        try:
            data = _udp_table(familia)
        except OSError:
            continue
        for port, pid in _rows(data, size, desloc):
            if pid in processes and port:
                found_ports.add(port)
    return found_ports


def game_ports(name: str = "SpiritVale.exe") -> set[int]:
    """Shortcut: find the process and return its ports in one go."""
    return ports_of(pids(name))
