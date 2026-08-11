"""Leitor do formato de serializacao do FishNet (o que o jogo manda pela rede).

Porte das primitivas usadas pelo spirit-vale-tools (MIT) pra Python. Sao poucas
e simples; o que da trabalho nao e ler os tipos, e saber a ORDEM dos campos
dentro do payload — isso vem do catalogo de RPCs do jogo.

O tipo central e o "packed": inteiro de tamanho variavel com zigzag, o mesmo
esquema do protobuf. Cada byte carrega 7 bits de dado; o bit mais alto diz se
ha continuacao. No fim, o zigzag desfaz o sinal — e por isso que -1 (usado como
"nulo" em string e lista) cabe num byte so.
"""

from __future__ import annotations

import struct


class PayloadTruncado(Exception):
    """Acabaram os bytes no meio de um campo."""


class PayloadInvalido(Exception):
    """O valor lido nao faz sentido pro campo (tamanho absurdo, utf-8 quebrado)."""


class Leitor:
    """Percorre o payload campo a campo, na ordem em que o jogo escreveu."""

    def __init__(self, dados: bytes):
        self.dados = dados
        self.pos = 0

    # -- controle ---------------------------------------------------------

    def _garantir(self, quantos: int) -> None:
        if self.pos + quantos > len(self.dados):
            raise PayloadTruncado(
                f"faltam bytes: pedi {quantos} em {self.pos}, "
                f"o payload tem {len(self.dados)}")

    @property
    def sobrou(self) -> int:
        return len(self.dados) - self.pos

    # -- tipos ------------------------------------------------------------

    def booleano(self) -> bool:
        self._garantir(1)
        valor = self.dados[self.pos] == 1
        self.pos += 1
        return valor

    def objeto(self) -> bool:
        """Marcador de objeto: um byte que diz se ele veio nulo.

        Invertido de proposito — no formato, 1 significa "e nulo".
        """
        return not self.booleano()

    def packed(self) -> int:
        """Inteiro de tamanho variavel com zigzag (igual ao protobuf)."""
        bruto = 0
        deslocamento = 0
        for _ in range(10):
            self._garantir(1)
            byte = self.dados[self.pos]
            self.pos += 1
            bruto |= (byte & 0x7F) << deslocamento
            if not byte & 0x80:
                # zigzag: pares viram positivos, impares viram negativos
                return (bruto >> 1) ^ -(bruto & 1)
            deslocamento += 7
        raise PayloadInvalido("inteiro packed sem fim (mais de 10 bytes)")

    def texto(self, tamanho_maximo: int) -> str | None:
        """String utf-8 precedida do tamanho. -1 significa nula."""
        tamanho = self.packed()
        if tamanho == -1:
            return None
        if tamanho < 0 or tamanho > tamanho_maximo:
            raise PayloadInvalido(f"tamanho de texto invalido: {tamanho}")
        self._garantir(tamanho)
        crus = self.dados[self.pos:self.pos + tamanho]
        self.pos += tamanho
        try:
            return crus.decode("utf-8")
        except UnicodeDecodeError as erro:
            raise PayloadInvalido(f"texto nao e utf-8 valido: {erro}") from erro

    def flutuante(self) -> float:
        self._garantir(4)
        valor = struct.unpack_from("<f", self.dados, self.pos)[0]
        self.pos += 4
        return valor

    def lista(self, ler_item) -> list:
        """Colecao precedida do tamanho. -1 significa vazia."""
        tamanho = self.packed()
        if tamanho == -1:
            return []
        if tamanho < 0 or tamanho > 100_000:
            raise PayloadInvalido(f"tamanho de lista invalido: {tamanho}")
        return [ler_item() for _ in range(tamanho)]

    def booleanos(self) -> list[bool]:
        return self.lista(self.booleano)

    def dicionario(self, ler_valor) -> None:
        """Percorre um dicionario de chave-texto, descartando o conteudo."""
        tamanho = self.packed()
        if tamanho == -1:
            return
        if tamanho < 0 or tamanho > 100_000:
            raise PayloadInvalido(f"tamanho de dicionario invalido: {tamanho}")
        for _ in range(tamanho):
            self.texto(256)
            ler_valor()

    # -- utilidade --------------------------------------------------------

    def pular(self, quantos: int) -> None:
        self._garantir(quantos)
        self.pos += quantos
