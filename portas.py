"""Quais portas UDP pertencem ao processo do jogo.

Sem isso a captura veria o trafego UDP da maquina inteira — navegador, Discord,
Windows Update — e tentaria decodificar tudo como se fosse do jogo. Perguntar
ao Windows de quem e cada socket e o filtro mais barato e mais honesto que
existe: em vez de adivinhar pelo formato do pacote, a gente pergunta o dono.

Uso o iphlpapi direto em vez de chamar netstat.exe porque abrir um processo a
cada segundo pisca uma janela de console na cara do usuario.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes as w

import memoria

iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)

AF_INET = 2
AF_INET6 = 23
UDP_TABLE_OWNER_PID = 1
ERRO_BUFFER_PEQUENO = 122          # ERROR_INSUFFICIENT_BUFFER

TAMANHO_LINHA_V4 = 12              # dwLocalAddr + dwLocalPort + dwOwningPid
TAMANHO_LINHA_V6 = 28              # 16 de endereco + escopo + porta + pid


def pids(nome: str) -> set[int]:
    """Todos os processos com esse nome (o jogo pode ter mais de uma janela)."""
    alvo = nome.lower().removesuffix(".exe")
    snap = memoria.k32.CreateToolhelp32Snapshot(memoria.TH32CS_SNAPPROCESS, 0)
    if snap == -1:
        return set()
    achados: set[int] = set()
    try:
        entrada = memoria.PROCESSENTRY32W()
        entrada.dwSize = ctypes.sizeof(entrada)
        if not memoria.k32.Process32FirstW(snap, ctypes.byref(entrada)):
            return achados
        while True:
            if entrada.szExeFile.lower().removesuffix(".exe") == alvo:
                achados.add(entrada.th32ProcessID)
            if not memoria.k32.Process32NextW(snap, ctypes.byref(entrada)):
                return achados
    finally:
        memoria.k32.CloseHandle(snap)


def _tabela_udp(familia: int) -> bytes:
    tamanho = w.DWORD(0)
    iphlpapi.GetExtendedUdpTable(None, ctypes.byref(tamanho), False,
                                 familia, UDP_TABLE_OWNER_PID, 0)
    if tamanho.value == 0:
        return b""
    buffer = ctypes.create_string_buffer(tamanho.value)
    codigo = iphlpapi.GetExtendedUdpTable(buffer, ctypes.byref(tamanho), False,
                                          familia, UDP_TABLE_OWNER_PID, 0)
    return buffer.raw if codigo == 0 else b""


def _porta(bruta: int) -> int:
    """O campo vem em ordem de rede; o Windows guarda num DWORD inteiro."""
    return ((bruta & 0xFF) << 8) | ((bruta >> 8) & 0xFF)


def _linhas(dados: bytes, tamanho_linha: int, deslocamento_porta: int):
    if len(dados) < 4:
        return
    quantas = int.from_bytes(dados[:4], "little")
    # o compilador alinha a primeira linha; em ambas as tabelas ela comeca em 4
    inicio = 4
    for i in range(quantas):
        base = inicio + i * tamanho_linha
        if base + tamanho_linha > len(dados):
            return
        linha = dados[base:base + tamanho_linha]
        porta = _porta(int.from_bytes(
            linha[deslocamento_porta:deslocamento_porta + 4], "little"))
        pid = int.from_bytes(linha[tamanho_linha - 4:tamanho_linha], "little")
        yield porta, pid


def portas_de(processos: set[int]) -> set[int]:
    """Portas UDP locais abertas por esses PIDs."""
    if not processos:
        return set()
    achadas: set[int] = set()
    for familia, tamanho, desloc in ((AF_INET, TAMANHO_LINHA_V4, 4),
                                     (AF_INET6, TAMANHO_LINHA_V6, 20)):
        try:
            dados = _tabela_udp(familia)
        except OSError:
            continue
        for porta, pid in _linhas(dados, tamanho, desloc):
            if pid in processos and porta:
                achadas.add(porta)
    return achadas


def portas_do_jogo(nome: str = "SpiritVale.exe") -> set[int]:
    """Atalho: acha o processo e devolve as portas dele numa tacada."""
    return portas_de(pids(nome))
