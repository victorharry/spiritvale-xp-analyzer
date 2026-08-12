"""Acesso ao Npcap por ctypes — sem pip install, so a DLL do sistema.

O Npcap e um driver de capture de rede; ele precisa estar instalado na maquina
(marcando "WinPcap API-compatible Mode"). Aqui a gente so CONVERSA com ele:
abre uma placa de rede, pede os packets que passam e fecha. Nada e enviado,
nada e modificado.

Escolhi ctypes em vez de scapy/npcap-python de proposito: a aplicacao vira um
.exe com PyInstaller, e cada dependencia nova e mais peso no instalador e mais
chance do antivirus reclamar.

Se o Npcap nao estiver instalado, `open_capture` levanta NpcapMissing com a instrucao
— e o unico erro aqui que o usuario consegue resolver sozinho.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import (POINTER, Structure, byref, c_char, c_char_p, c_int,
                    c_uint, c_ushort, c_void_p)
from dataclasses import dataclass, field

ERRBUF_SIZE = 256          # PCAP_ERRBUF_SIZE
SNAPLEN = 65535
TIMEOUT_MS = 100             # quanto next_packet() bloqueia antes de devolver nada

# tipos de link_type que sabemos desembrulhar (pcap_datalink)
LINK_ETHERNET = 1
LINK_NULL = 0
LINK_RAW = 12
LINK_LOOPBACK_BSD = 108


class PcapError(Exception):
    """Qualquer falha vinda da library de capture."""


class NpcapMissing(PcapError):
    """A DLL nao esta na maquina — o unico erro que o usuario resolve sozinho."""


# -- estruturas da libpcap ------------------------------------------------

class _Timeval(Structure):
    # no Windows a libpcap usa long de 32 bits nos dois campos
    _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]


class _PcapHeader(Structure):
    _fields_ = [("ts", _Timeval), ("caplen", c_uint), ("len", c_uint)]


class _Sockaddr(Structure):
    # sa_data tem que ser c_ubyte, NAO c_char: um array de c_char vira bytes
    # cortado no primeiro zero, e ai um IP como 10.0.0.5 (ou qualquer port
    # zerada antes dele) simplesmente some
    _fields_ = [("sa_family", c_ushort), ("sa_data", ctypes.c_ubyte * 26)]


class _PcapAddr(Structure):
    pass


_PcapAddr._fields_ = [
    ("next", POINTER(_PcapAddr)),
    ("addr", POINTER(_Sockaddr)),
    ("netmask", POINTER(_Sockaddr)),
    ("broadaddr", POINTER(_Sockaddr)),
    ("dstaddr", POINTER(_Sockaddr)),
]


class _PcapIf(Structure):
    pass


_PcapIf._fields_ = [
    ("next", POINTER(_PcapIf)),
    ("name", c_char_p),
    ("description", c_char_p),
    ("addresses", POINTER(_PcapAddr)),
    ("flags", c_uint),
]


class _BpfProgram(Structure):
    _fields_ = [("bf_len", c_uint), ("bf_insns", c_void_p)]


# -- carga da DLL ---------------------------------------------------------

_lib = None


def _npcap_folder() -> str:
    raiz = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(raiz, "System32", "Npcap")


def library():
    """Carrega a wpcap.dll uma vez e devolve o handle ja com assinaturas."""
    global _lib
    if _lib is not None:
        return _lib

    # a instalacao padrao do Npcap poe as DLLs numa subpasta propria; sem
    # record essa pasta, a wpcap acha mas a Packet.dll ao lado nao
    pasta = _npcap_folder()
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
        raise NpcapMissing(
            "Npcap nao encontrado. Instale de https://npcap.com "
            "marcando a opcao 'WinPcap API-compatible Mode'."
        ) from ultimo_erro

    _declare_types(_lib)
    return _lib


def _declare_types(lib) -> None:
    """Diz ao ctypes o formato de cada funcao — sem isso, ponteiro de 64 bits
    volta truncado em 32 e o processo morre de forma misteriosa."""
    lib.pcap_lib_version.restype = c_char_p
    lib.pcap_findalldevs.argtypes = [POINTER(POINTER(_PcapIf)), c_char_p]
    lib.pcap_findalldevs.restype = c_int
    lib.pcap_freealldevs.argtypes = [POINTER(_PcapIf)]
    lib.pcap_freealldevs.restype = None
    lib.pcap_create.argtypes = [c_char_p, c_char_p]
    lib.pcap_create.restype = c_void_p
    for name in ("pcap_set_snaplen", "pcap_set_promisc", "pcap_set_timeout",
                 "pcap_set_buffer_size", "pcap_set_immediate_mode"):
        if hasattr(lib, name):
            getattr(lib, name).argtypes = [c_void_p, c_int]
            getattr(lib, name).restype = c_int
    lib.pcap_activate.argtypes = [c_void_p]
    lib.pcap_activate.restype = c_int
    lib.pcap_datalink.argtypes = [c_void_p]
    lib.pcap_datalink.restype = c_int
    lib.pcap_compile.argtypes = [c_void_p, POINTER(_BpfProgram), c_char_p, c_int, c_uint]
    lib.pcap_compile.restype = c_int
    lib.pcap_setfilter.argtypes = [c_void_p, POINTER(_BpfProgram)]
    lib.pcap_setfilter.restype = c_int
    lib.pcap_freecode.argtypes = [POINTER(_BpfProgram)]
    lib.pcap_freecode.restype = None
    lib.pcap_next_ex.argtypes = [c_void_p, POINTER(POINTER(_PcapHeader)), POINTER(POINTER(c_char))]
    lib.pcap_next_ex.restype = c_int
    lib.pcap_geterr.argtypes = [c_void_p]
    lib.pcap_geterr.restype = c_char_p
    lib.pcap_close.argtypes = [c_void_p]
    lib.pcap_close.restype = None
    lib.pcap_breakloop.argtypes = [c_void_p]
    lib.pcap_breakloop.restype = None


def available() -> bool:
    try:
        library()
        return True
    except PcapError:
        return False


def version() -> str:
    return library().pcap_lib_version().decode("latin-1", "replace")


# -- placas de rede -------------------------------------------------------

@dataclass
class Device:
    name: str
    description: str
    addresses: list[str] = field(default_factory=list)
    loopback: bool = False

    def __str__(self) -> str:
        ips = ", ".join(self.addresses) or "sem IP"
        return f"{self.description or self.name} ({ips})"


def _read_address(sa: _Sockaddr) -> str | None:
    if sa.sa_family == 2:                      # AF_INET
        octets = sa.sa_data[2:6]
        return ".".join(str(b) for b in octets)
    if sa.sa_family == 23:                     # AF_INET6 no Windows
        raw_bytes = sa.sa_data[6:22]
        if len(raw_bytes) < 16:
            return None
        parts = [f"{raw_bytes[i] << 8 | raw_bytes[i + 1]:x}" for i in range(0, 16, 2)]
        return ":".join(parts)
    return None


def devices() -> list[Device]:
    lib = library()
    erro = ctypes.create_string_buffer(ERRBUF_SIZE)
    head = POINTER(_PcapIf)()
    if lib.pcap_findalldevs(byref(head), erro) != 0:
        raise PcapError(erro.value.decode("latin-1", "replace"))

    out: list[Device] = []
    try:
        current = head
        while current:
            item = current.contents
            addresses = []
            address = item.addresses
            while address:
                if address.contents.addr:
                    text = _read_address(address.contents.addr.contents)
                    if text:
                        addresses.append(text)
                address = address.contents.next
            out.append(Device(
                name=(item.name or b"").decode("latin-1", "replace"),
                description=(item.description or b"").decode("latin-1", "replace"),
                addresses=addresses,
                loopback=bool(item.flags & 1),   # PCAP_IF_LOOPBACK
            ))
            current = item.next
    finally:
        lib.pcap_freealldevs(head)
    return out


_UNWANTED = ("bluetooth", "wan miniport", "vmware", "hyper-v",
                "zerotier", "virtualbox", "tap-windows", "loopback")


def _outbound_ip() -> str | None:
    """Descobre qual IP local o Windows usaria pra falar com a internet.

    Truque classico: um socket UDP "conectado" nao envia nada — so faz o
    sistema pick a rota. E de longe o jeito mais barato de saber qual das
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


def pick(list_of: list[Device] | None = None) -> Device | None:
    """A placa por onde o trafego do jogo passa."""
    list_of = list_of if list_of is not None else devices()
    out = _outbound_ip()
    if out:
        for device in list_of:
            if out in device.addresses:
                return device
    for device in list_of:
        label = f"{device.name} {device.description}".lower()
        if (not device.loopback and device.addresses
                and not any(ruim in label for ruim in _UNWANTED)):
            return device
    return list_of[0] if list_of else None


# -- session de capture ----------------------------------------------------

class Session:
    """Uma placa aberta. Use como contexto: `with pcap.open_capture() as session:`."""

    def __init__(self, handle, link_type: int, device: Device):
        self._lib = library()
        self._handle = handle
        self.link_type = link_type
        self.device = device
        self._cabecalho = POINTER(_PcapHeader)()
        self._dados = POINTER(c_char)()

    def next_packet(self) -> bytes | None:
        """Um packet cru, ou None se nada chegou dentro da espera."""
        if self._handle is None:
            return None
        resultado = self._lib.pcap_next_ex(
            self._handle, byref(self._cabecalho), byref(self._dados))
        if resultado == 1:
            size = self._cabecalho.contents.caplen
            return ctypes.string_at(self._dados, size)
        if resultado == 0:
            return None                          # so o tempo de espera estourou
        if resultado == -2:
            return None                          # pcap_breakloop
        raise PcapError(self._erro())

    def _erro(self) -> str:
        rawsocket = self._lib.pcap_geterr(self._handle)
        return (rawsocket or b"erro desconhecido").decode("latin-1", "replace")

    def interrupt(self) -> None:
        """Faz o next_packet() pendente voltar — chamavel de outra thread."""
        if self._handle is not None:
            self._lib.pcap_breakloop(self._handle)

    def close(self) -> None:
        if self._handle is not None:
            self._lib.pcap_close(self._handle)
            self._handle = None

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_) -> None:
        self.close()


def open_capture(device: Device | None = None, bpf_filter: str = "udp") -> Session:
    """Abre a placa em modo nao-promiscuo (so o trafego desta maquina)."""
    lib = library()
    device = device or pick()
    if device is None:
        raise PcapError("nenhuma placa de rede available para capture")

    erro = ctypes.create_string_buffer(ERRBUF_SIZE)
    handle = lib.pcap_create(device.name.encode("latin-1"), erro)
    if not handle:
        raise PcapError(erro.value.decode("latin-1", "replace"))

    try:
        lib.pcap_set_snaplen(handle, SNAPLEN)
        lib.pcap_set_promisc(handle, 0)
        lib.pcap_set_timeout(handle, TIMEOUT_MS)
        lib.pcap_set_buffer_size(handle, 8 * 1024 * 1024)
        if hasattr(lib, "pcap_set_immediate_mode"):
            lib.pcap_set_immediate_mode(handle, 1)

        code = lib.pcap_activate(handle)
        if code < 0:
            rawsocket = lib.pcap_geterr(handle) or b""
            raise PcapError(
                f"nao consegui open_capture '{device.description or device.name}': "
                f"{rawsocket.decode('latin-1', 'replace')} (code {code})")

        link_type = lib.pcap_datalink(handle)
        if bpf_filter:
            program = _BpfProgram()
            if lib.pcap_compile(handle, byref(program),
                                bpf_filter.encode("ascii"), 1, 0xFFFFFFFF) == 0:
                lib.pcap_setfilter(handle, byref(program))
                lib.pcap_freecode(byref(program))
    except Exception:
        lib.pcap_close(handle)
        raise

    return Session(handle, link_type, device)


# -- desembrulho do link_type ------------------------------------------------

def strip_link_layer(frame: bytes, link_type: int) -> bytes | None:
    """Tira o cabecalho da placa e devolve o packet IP puro."""
    if link_type == LINK_ETHERNET:
        if len(frame) < 14:
            return None
        kind = int.from_bytes(frame[12:14], "big")
        pos = 14
        while kind in (0x8100, 0x88A8, 0x9100):     # VLAN empilhada
            if len(frame) < pos + 4:
                return None
            kind = int.from_bytes(frame[pos + 2:pos + 4], "big")
            pos += 4
        if kind not in (0x0800, 0x86DD):
            return None
        return frame[pos:]
    if link_type in (LINK_NULL, LINK_LOOPBACK_BSD):
        return frame[4:] if len(frame) > 4 else None
    if link_type == LINK_RAW:
        return frame
    return None
