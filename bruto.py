"""Captura sem instalar nada: raw socket do proprio Windows.

Alternativa ao Npcap. `SIO_RCVALL` poe o socket em modo de captura e entrega
todo pacote IP que passa pela placa — sem driver, sem download, sem segundo
instalador.

O preco e outro, e nao e pequeno: **exige rodar como administrador**. Sem
elevacao o Windows recusa o socket com WinError 10013, e nao ha contorno — a
restricao e do sistema, nao da API. Entao os dois caminhos existem lado a lado
e o app usa o que estiver disponivel:

    Npcap instalado  -> abre normal, sem UAC nenhuma vez
    rodando elevado  -> nao precisa de Npcap
    nenhum dos dois  -> o app diz o que fazer

Diferenca pratica pra quem le o resultado: aqui NAO ha cabecalho Ethernet. O
que chega ja comeca no cabecalho IP, entao o tipo de enlace declarado e
ENLACE_CRU e `pcap.pacote_ip` devolve o pacote intacto.
"""

from __future__ import annotations

import ctypes
import socket

import pcap

# o que sai daqui ja e pacote IP puro, sem cabecalho de placa
ENLACE = pcap.ENLACE_CRU

ESPERA = 0.2          # segundos que proximo() bloqueia antes de devolver nada


class SemPermissao(pcap.ErroPcap):
    """Falta elevacao. E o unico erro aqui que o usuario resolve sozinho."""


def elevado() -> bool:
    """Estamos rodando como administrador?"""
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _ip_de_saida() -> str | None:
    """Qual IP local o Windows usa pra falar com a internet.

    Um socket UDP "conectado" nao envia nada — so faz o sistema escolher a
    rota. E o jeito mais barato de saber em qual placa amarrar a captura.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


class Sessao:
    """Mesma interface da sessao do pcap, pra `captura` nao precisar saber
    qual das duas esta usando."""

    def __init__(self, socket_bruto, endereco: str):
        self._socket = socket_bruto
        self.enlace = ENLACE
        self.dispositivo = f"raw socket em {endereco} (sem Npcap)"

    def proximo(self) -> bytes | None:
        if self._socket is None:
            return None
        try:
            dados, _ = self._socket.recvfrom(65535)
            return dados
        except socket.timeout:
            return None
        except OSError:
            return None

    def interromper(self) -> None:
        """Solta um proximo() pendente — chamavel de outra thread."""
        self.fechar()

    def fechar(self) -> None:
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

    def __enter__(self) -> "Sessao":
        return self

    def __exit__(self, *_) -> None:
        self.fechar()


def disponivel() -> bool:
    """Da pra usar este caminho agora? (so com elevacao)"""
    return elevado()


def abrir() -> Sessao:
    endereco = _ip_de_saida()
    if not endereco:
        raise pcap.ErroPcap("nao consegui descobrir o IP local desta maquina")

    try:
        bruto = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_IP)
        bruto.bind((endereco, 0))
        bruto.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
        bruto.ioctl(socket.SIO_RCVALL, socket.RCVALL_ON)
        bruto.settimeout(ESPERA)
    except PermissionError as erro:
        raise SemPermissao(
            "captura por raw socket exige administrador. Rode o XP Analyzer "
            "como administrador, ou instale o Npcap (https://npcap.com) e "
            "abra normal."
        ) from erro
    except OSError as erro:
        raise pcap.ErroPcap(f"nao consegui abrir o raw socket: {erro}") from erro

    return Sessao(bruto, endereco)
