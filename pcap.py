"""Acesso ao Npcap por ctypes — sem pip install, so a DLL do sistema.

O Npcap e um driver de captura de rede; ele precisa estar instalado na maquina
(marcando "WinPcap API-compatible Mode"). Aqui a gente so CONVERSA com ele:
abre uma placa de rede, pede os pacotes que passam e fecha. Nada e enviado,
nada e modificado.

Escolhi ctypes em vez de scapy/npcap-python de proposito: a aplicacao vira um
.exe com PyInstaller, e cada dependencia nova e mais peso no instalador e mais
chance do antivirus reclamar.

Se o Npcap nao estiver instalado, `abrir` levanta NpcapAusente com a instrucao
— e o unico erro aqui que o usuario consegue resolver sozinho.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import (POINTER, Structure, byref, c_char, c_char_p, c_int,
                    c_uint, c_ushort, c_void_p)
from dataclasses import dataclass, field

TAMANHO_ERRO = 256          # PCAP_ERRBUF_SIZE
SNAPLEN = 65535
ESPERA_MS = 100             # quanto proximo() bloqueia antes de devolver nada

# tipos de enlace que sabemos desembrulhar (pcap_datalink)
ENLACE_ETHERNET = 1
ENLACE_NULO = 0
ENLACE_CRU = 12
ENLACE_LOOPBACK_BSD = 108


class ErroPcap(Exception):
    """Qualquer falha vinda da biblioteca de captura."""


class NpcapAusente(ErroPcap):
    """A DLL nao esta na maquina — o unico erro que o usuario resolve sozinho."""


# -- estruturas da libpcap ------------------------------------------------

class _Timeval(Structure):
    # no Windows a libpcap usa long de 32 bits nos dois campos
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _Cabecalho(Structure):
    _fields_ = [("ts", _Timeval), ("caplen", c_uint), ("len", c_uint)]


class _Sockaddr(Structure):
    # sa_data tem que ser c_ubyte, NAO c_char: um array de c_char vira bytes
    # cortado no primeiro zero, e ai um IP como 10.0.0.5 (ou qualquer porta
    # zerada antes dele) simplesmente some
    _fields_ = [("sa_family", c_ushort), ("sa_data", ctypes.c_ubyte * 26)]


class _Endereco(Structure):
    pass


_Endereco._fields_ = [
    ("next", POINTER(_Endereco)),
    ("addr", POINTER(_Sockaddr)),
    ("netmask", POINTER(_Sockaddr)),
    ("broadaddr", POINTER(_Sockaddr)),
    ("dstaddr", POINTER(_Sockaddr)),
]


class _Interface(Structure):
    pass


_Interface._fields_ = [
    ("next", POINTER(_Interface)),
    ("name", c_char_p),
    ("description", c_char_p),
    ("addresses", POINTER(_Endereco)),
    ("flags", c_uint),
]


class _ProgramaBpf(Structure):
    _fields_ = [("bf_len", c_uint), ("bf_insns", c_void_p)]


# -- carga da DLL ---------------------------------------------------------

_lib = None


def _pasta_npcap() -> str:
    raiz = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(raiz, "System32", "Npcap")


def biblioteca():
    """Carrega a wpcap.dll uma vez e devolve o handle ja com assinaturas."""
    global _lib
    if _lib is not None:
        return _lib

    # a instalacao padrao do Npcap poe as DLLs numa subpasta propria; sem
    # registrar essa pasta, a wpcap acha mas a Packet.dll ao lado nao
    pasta = _pasta_npcap()
    if os.path.isdir(pasta):
        try:
            os.add_dll_directory(pasta)
        except OSError:
            pass

    ultimo_erro = None
    for caminho in ("wpcap.dll", os.path.join(pasta, "wpcap.dll")):
        try:
            _lib = ctypes.CDLL(caminho)
            break
        except OSError as erro:
            ultimo_erro = erro
    else:
        raise NpcapAusente(
            "Npcap nao encontrado. Instale de https://npcap.com "
            "marcando a opcao 'WinPcap API-compatible Mode'."
        ) from ultimo_erro

    _assinar(_lib)
    return _lib


def _assinar(lib) -> None:
    """Diz ao ctypes o formato de cada funcao — sem isso, ponteiro de 64 bits
    volta truncado em 32 e o processo morre de forma misteriosa."""
    lib.pcap_lib_version.restype = c_char_p
    lib.pcap_findalldevs.argtypes = [POINTER(POINTER(_Interface)), c_char_p]
    lib.pcap_findalldevs.restype = c_int
    lib.pcap_freealldevs.argtypes = [POINTER(_Interface)]
    lib.pcap_freealldevs.restype = None
    lib.pcap_create.argtypes = [c_char_p, c_char_p]
    lib.pcap_create.restype = c_void_p
    for nome in ("pcap_set_snaplen", "pcap_set_promisc", "pcap_set_timeout",
                 "pcap_set_buffer_size", "pcap_set_immediate_mode"):
        if hasattr(lib, nome):
            getattr(lib, nome).argtypes = [c_void_p, c_int]
            getattr(lib, nome).restype = c_int
    lib.pcap_activate.argtypes = [c_void_p]
    lib.pcap_activate.restype = c_int
    lib.pcap_datalink.argtypes = [c_void_p]
    lib.pcap_datalink.restype = c_int
    lib.pcap_compile.argtypes = [c_void_p, POINTER(_ProgramaBpf), c_char_p, c_int, c_uint]
    lib.pcap_compile.restype = c_int
    lib.pcap_setfilter.argtypes = [c_void_p, POINTER(_ProgramaBpf)]
    lib.pcap_setfilter.restype = c_int
    lib.pcap_freecode.argtypes = [POINTER(_ProgramaBpf)]
    lib.pcap_freecode.restype = None
    lib.pcap_next_ex.argtypes = [c_void_p, POINTER(POINTER(_Cabecalho)), POINTER(POINTER(c_char))]
    lib.pcap_next_ex.restype = c_int
    lib.pcap_geterr.argtypes = [c_void_p]
    lib.pcap_geterr.restype = c_char_p
    lib.pcap_close.argtypes = [c_void_p]
    lib.pcap_close.restype = None
    lib.pcap_breakloop.argtypes = [c_void_p]
    lib.pcap_breakloop.restype = None


def disponivel() -> bool:
    try:
        biblioteca()
        return True
    except ErroPcap:
        return False


def versao() -> str:
    return biblioteca().pcap_lib_version().decode("latin-1", "replace")


# -- placas de rede -------------------------------------------------------

@dataclass
class Dispositivo:
    nome: str
    descricao: str
    enderecos: list[str] = field(default_factory=list)
    loopback: bool = False

    def __str__(self) -> str:
        ips = ", ".join(self.enderecos) or "sem IP"
        return f"{self.descricao or self.nome} ({ips})"


def _ler_endereco(sa: _Sockaddr) -> str | None:
    if sa.sa_family == 2:                      # AF_INET
        octetos = sa.sa_data[2:6]
        return ".".join(str(b) for b in octetos)
    if sa.sa_family == 23:                     # AF_INET6 no Windows
        crus = sa.sa_data[6:22]
        if len(crus) < 16:
            return None
        partes = [f"{crus[i] << 8 | crus[i + 1]:x}" for i in range(0, 16, 2)]
        return ":".join(partes)
    return None


def dispositivos() -> list[Dispositivo]:
    lib = biblioteca()
    erro = ctypes.create_string_buffer(TAMANHO_ERRO)
    cabeca = POINTER(_Interface)()
    if lib.pcap_findalldevs(byref(cabeca), erro) != 0:
        raise ErroPcap(erro.value.decode("latin-1", "replace"))

    saida: list[Dispositivo] = []
    try:
        atual = cabeca
        while atual:
            item = atual.contents
            enderecos = []
            endereco = item.addresses
            while endereco:
                if endereco.contents.addr:
                    texto = _ler_endereco(endereco.contents.addr.contents)
                    if texto:
                        enderecos.append(texto)
                endereco = endereco.contents.next
            saida.append(Dispositivo(
                nome=(item.name or b"").decode("latin-1", "replace"),
                descricao=(item.description or b"").decode("latin-1", "replace"),
                enderecos=enderecos,
                loopback=bool(item.flags & 1),   # PCAP_IF_LOOPBACK
            ))
            atual = item.next
    finally:
        lib.pcap_freealldevs(cabeca)
    return saida


_INDESEJADOS = ("bluetooth", "wan miniport", "vmware", "hyper-v",
                "zerotier", "virtualbox", "tap-windows", "loopback")


def _ip_de_saida() -> str | None:
    """Descobre qual IP local o Windows usaria pra falar com a internet.

    Truque classico: um socket UDP "conectado" nao envia nada — so faz o
    sistema escolher a rota. E de longe o jeito mais barato de saber qual das
    seis placas listadas e a que o jogo realmente usa.
    """
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 53))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def escolher(lista: list[Dispositivo] | None = None) -> Dispositivo | None:
    """A placa por onde o trafego do jogo passa."""
    lista = lista if lista is not None else dispositivos()
    saida = _ip_de_saida()
    if saida:
        for dispositivo in lista:
            if saida in dispositivo.enderecos:
                return dispositivo
    for dispositivo in lista:
        rotulo = f"{dispositivo.nome} {dispositivo.descricao}".lower()
        if (not dispositivo.loopback and dispositivo.enderecos
                and not any(ruim in rotulo for ruim in _INDESEJADOS)):
            return dispositivo
    return lista[0] if lista else None


# -- sessao de captura ----------------------------------------------------

class Sessao:
    """Uma placa aberta. Use como contexto: `with pcap.abrir() as sessao:`."""

    def __init__(self, handle, enlace: int, dispositivo: Dispositivo):
        self._lib = biblioteca()
        self._handle = handle
        self.enlace = enlace
        self.dispositivo = dispositivo
        self._cabecalho = POINTER(_Cabecalho)()
        self._dados = POINTER(c_char)()

    def proximo(self) -> bytes | None:
        """Um pacote cru, ou None se nada chegou dentro da espera."""
        if self._handle is None:
            return None
        resultado = self._lib.pcap_next_ex(
            self._handle, byref(self._cabecalho), byref(self._dados))
        if resultado == 1:
            tamanho = self._cabecalho.contents.caplen
            return ctypes.string_at(self._dados, tamanho)
        if resultado == 0:
            return None                          # so o tempo de espera estourou
        if resultado == -2:
            return None                          # pcap_breakloop
        raise ErroPcap(self._erro())

    def _erro(self) -> str:
        bruto = self._lib.pcap_geterr(self._handle)
        return (bruto or b"erro desconhecido").decode("latin-1", "replace")

    def interromper(self) -> None:
        """Faz o proximo() pendente voltar — chamavel de outra thread."""
        if self._handle is not None:
            self._lib.pcap_breakloop(self._handle)

    def fechar(self) -> None:
        if self._handle is not None:
            self._lib.pcap_close(self._handle)
            self._handle = None

    def __enter__(self) -> "Sessao":
        return self

    def __exit__(self, *_) -> None:
        self.fechar()


def abrir(dispositivo: Dispositivo | None = None, filtro: str = "udp") -> Sessao:
    """Abre a placa em modo nao-promiscuo (so o trafego desta maquina)."""
    lib = biblioteca()
    dispositivo = dispositivo or escolher()
    if dispositivo is None:
        raise ErroPcap("nenhuma placa de rede disponivel para captura")

    erro = ctypes.create_string_buffer(TAMANHO_ERRO)
    handle = lib.pcap_create(dispositivo.nome.encode("latin-1"), erro)
    if not handle:
        raise ErroPcap(erro.value.decode("latin-1", "replace"))

    try:
        lib.pcap_set_snaplen(handle, SNAPLEN)
        lib.pcap_set_promisc(handle, 0)
        lib.pcap_set_timeout(handle, ESPERA_MS)
        lib.pcap_set_buffer_size(handle, 8 * 1024 * 1024)
        if hasattr(lib, "pcap_set_immediate_mode"):
            lib.pcap_set_immediate_mode(handle, 1)

        codigo = lib.pcap_activate(handle)
        if codigo < 0:
            bruto = lib.pcap_geterr(handle) or b""
            raise ErroPcap(
                f"nao consegui abrir '{dispositivo.descricao or dispositivo.nome}': "
                f"{bruto.decode('latin-1', 'replace')} (codigo {codigo})")

        enlace = lib.pcap_datalink(handle)
        if filtro:
            programa = _ProgramaBpf()
            if lib.pcap_compile(handle, byref(programa),
                                filtro.encode("ascii"), 1, 0xFFFFFFFF) == 0:
                lib.pcap_setfilter(handle, byref(programa))
                lib.pcap_freecode(byref(programa))
    except Exception:
        lib.pcap_close(handle)
        raise

    return Sessao(handle, enlace, dispositivo)


# -- desembrulho do enlace ------------------------------------------------

def pacote_ip(quadro: bytes, enlace: int) -> bytes | None:
    """Tira o cabecalho da placa e devolve o pacote IP puro."""
    if enlace == ENLACE_ETHERNET:
        if len(quadro) < 14:
            return None
        tipo = int.from_bytes(quadro[12:14], "big")
        pos = 14
        while tipo in (0x8100, 0x88A8, 0x9100):     # VLAN empilhada
            if len(quadro) < pos + 4:
                return None
            tipo = int.from_bytes(quadro[pos + 2:pos + 4], "big")
            pos += 4
        if tipo not in (0x0800, 0x86DD):
            return None
        return quadro[pos:]
    if enlace in (ENLACE_NULO, ENLACE_LOOPBACK_BSD):
        return quadro[4:] if len(quadro) > 4 else None
    if enlace == ENLACE_CRU:
        return quadro
    return None
