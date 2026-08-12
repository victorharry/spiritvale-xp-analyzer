"""Captura sem instalar nada: raw socket do proprio Windows.

Alternativa ao Npcap. `SIO_RCVALL` poe o socket em modo de capture e entrega
todo packet IP que passa pela placa — sem driver, sem download, sem segundo
instalador.

O preco e outro, e nao e pequeno: **exige rodar como administrador**. Sem
elevacao o Windows recusa o socket com WinError 10013, e nao ha contorno — a
restricao e do sistema, nao da API. Entao os dois caminhos existem lado a lado
e o app usa o que estiver available:

    Npcap instalado  -> abre normal, sem UAC nenhuma vez
    rodando is_elevated  -> nao precisa de Npcap
    nenhum dos dois  -> o app diz o que fazer

Diferenca pratica pra quem le o resultado: aqui NAO ha cabecalho Ethernet. O
que chega ja comeca no cabecalho IP, entao o kind de link_type declared e
LINK_RAW e `pcap.strip_link_layer` devolve o packet intacto.
"""

from __future__ import annotations

import ctypes
import socket

import pcap

# o que sai daqui ja e packet IP puro, sem cabecalho de placa
LINK_TYPE = pcap.LINK_RAW

TIMEOUT = 0.2          # seconds que next_packet() bloqueia antes de devolver nada


class NeedsAdmin(pcap.PcapError):
    """Falta elevacao. E o unico erro aqui que o usuario resolve sozinho."""


def is_elevated() -> bool:
    """Estamos rodando como administrador?"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _outbound_ip() -> str | None:
    """Qual IP local o Windows usa pra falar com a internet.

    Um socket UDP "conectado" nao envia nada — so faz o sistema pick a
    rota. E o jeito mais barato de saber em qual placa amarrar a capture.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


class Session:
    """Mesma interface da session do pcap, pra `capture` nao precisar saber
    qual das duas esta usando."""

    def __init__(self, raw, address: str):
        self._socket = raw
        self.link_type = LINK_TYPE
        self.device = f"raw socket em {address} (sem Npcap)"

    def next_packet(self) -> bytes | None:
        if self._socket is None:
            return None
        try:
            data, _ = self._socket.recvfrom(65535)
            return data
        except socket.timeout:
            return None
        except OSError:
            return None

    def interrupt(self) -> None:
        """Solta um next_packet() pendente — chamavel de outra thread."""
        self.close()

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.ioctl(socket.SIO_RCVALL, socket.RCVALL_OFF)
        except OSError:
            pass
        try:
            self._socket.close()
        except OSError:
            pass
        self._socket = None

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def available() -> bool:
    """Da pra usar este caminho agora? (so com elevacao)"""
    return is_elevated()


def open_capture() -> Session:
    address = _outbound_ip()
    if not address:
        raise pcap.PcapError("nao consegui descobrir o IP local desta maquina")

    try:
        rawsocket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
        rawsocket.bind((address, 0))
        rawsocket.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        rawsocket.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
        rawsocket.settimeout(TIMEOUT)
    except PermissionError as erro:
        raise NeedsAdmin(
            "capture por raw socket exige administrador. Rode o XP Analyzer "
            "como administrador, ou instale o Npcap (https://npcap.com) e "
            "abra normal."
        ) from erro
    except OSError as erro:
        raise pcap.PcapError(f"nao consegui open_capture o raw socket: {erro}") from erro

    return Session(rawsocket, address)
