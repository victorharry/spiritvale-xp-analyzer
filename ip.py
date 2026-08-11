"""Desembrulha IP e UDP — o pacote cru vira "isto veio de tal porta".

Porte enxuto do packet-parser do spirit-vale-tools (MIT). So o que a captura
precisa: descartar o que nao e UDP e entregar o conteudo com as portas.

Um detalhe que parece pedantismo mas nao e: pacotes IP fragmentados (offset
diferente de zero) sao descartados. Um fragmento do meio nao tem cabecalho UDP;
lido como se tivesse, ele vira um datagrama inventado com portas aleatorias.
"""

from __future__ import annotations

from dataclasses import dataclass

PROTOCOLO_UDP = 17
EXTENSOES_IPV6 = (0, 43, 44, 51, 60)


@dataclass(frozen=True)
class Datagrama:
    porta_origem: int
    porta_destino: int
    dados: bytes

    def envolve(self, portas: set[int]) -> bool:
        return self.porta_origem in portas or self.porta_destino in portas

    @property
    def entrando(self) -> bool:
        """Heuristica so pra rotular: pacote do servidor chega numa porta alta
        local vinda da porta do servidor. Quem decide de verdade e o chamador,
        que sabe quais portas sao do jogo."""
        return True


def analisar(pacote: bytes) -> Datagrama | None:
    if len(pacote) < 20:
        return None
    versao = pacote[0] >> 4
    if versao == 4:
        return _ipv4(pacote)
    if versao == 6:
        return _ipv6(pacote)
    return None


def _ipv4(pacote: bytes) -> Datagrama | None:
    tamanho_cabecalho = (pacote[0] & 0x0F) * 4
    if tamanho_cabecalho < 20 or tamanho_cabecalho > len(pacote):
        return None
    if pacote[9] != PROTOCOLO_UDP:
        return None
    fragmento = int.from_bytes(pacote[6:8], "big")
    if fragmento & 0x1FFF:                      # nao e o primeiro fragmento
        return None
    declarado = int.from_bytes(pacote[2:4], "big")
    if declarado < tamanho_cabecalho:
        return None
    fim = min(declarado, len(pacote))
    return _udp(pacote, tamanho_cabecalho, fim)


def _ipv6(pacote: bytes) -> Datagrama | None:
    if len(pacote) < 40:
        return None
    declarado = 40 + int.from_bytes(pacote[4:6], "big")
    fim = min(declarado, len(pacote))
    proximo = pacote[6]
    pos = 40
    while proximo in EXTENSOES_IPV6:
        if pos + 2 > fim:
            return None
        atual, proximo = proximo, pacote[pos]
        if atual == 44:                          # cabecalho de fragmento
            return None
        comprimento = (pacote[pos + 1] + 2) * 4 if atual == 51 else (pacote[pos + 1] + 1) * 8
        pos += comprimento
        if pos > fim:
            return None
    if proximo != PROTOCOLO_UDP:
        return None
    return _udp(pacote, pos, fim)


def _udp(pacote: bytes, inicio: int, fim: int) -> Datagrama | None:
    if inicio + 8 > fim:
        return None
    comprimento = int.from_bytes(pacote[inicio + 4:inicio + 6], "big")
    if comprimento < 8:
        return None
    final = min(inicio + comprimento, fim)
    return Datagrama(
        porta_origem=int.from_bytes(pacote[inicio:inicio + 2], "big"),
        porta_destino=int.from_bytes(pacote[inicio + 2:inicio + 4], "big"),
        dados=pacote[inicio + 8:final],
    )
