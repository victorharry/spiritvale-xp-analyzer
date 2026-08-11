"""Camada FishNet — e aqui que a gente cava atras do CharacterData.

Duas coisas acontecem neste arquivo.

**Remontagem de split.** Quando uma mensagem do FishNet nao cabe num pacote so,
ela vai como `split`: varios pedacos com o mesmo tick, numerados. O
CharacterData e grande o bastante pra cair nesse caminho com frequencia.

**A cacada.** Aqui eu tomei um atalho deliberado, e vale explicar por que.

O decodificador completo deles resolve cada RPC pelo nome: le o mapa de 4 mil
linhas de RPCs, acompanha os `objectSpawn` pra saber qual "link id" virou qual
metodo, e so entao sabe onde comeca o conteudo do CharacterCallback_T. E o
jeito certo se voce quer ler o protocolo inteiro. Nos queremos UM campo.

Entao, em vez de resolver o protocolo, a gente tenta decodificar CharacterData
a partir de cada posicao plausivel do pacote. O que segura a mentira e o
proprio decodificador: pra um trecho passar, ele tem que conter seis strings
utf-8 validas com tamanho dentro do limite, e terminar em nivel 1..150 e job
1..70. Lixo nao passa nesse funil — e o que passar por acidente ainda tem que
repetir o mesmo nome de personagem pra ser levado a serio (ver `Cacador`).

O custo disso e o teto: se um dia precisarmos de outros campos, ai vale portar
a resolucao de RPC de verdade.
"""

from __future__ import annotations

from dataclasses import dataclass

import personagem
from personagem import Progresso

PACOTE_SPLIT = 2
CABECALHO = 6                # 4 de tick + 2 de id do pacote

PEDACOS_MAXIMOS = 1024
BYTES_MAXIMOS = 1024 * 1024
SPLITS_SIMULTANEOS = 32

# tamanho minimo pra valer a tentativa: dois UIDs, dois textos e o nome ja
# passam disso com folga
MINIMO_PLAUSIVEL = 100
TAMANHO_MAXIMO_UID = 80


def _packed(dados: bytes, pos: int) -> tuple[int, int] | None:
    """Le um inteiro packed com zigzag. Devolve (valor, proxima posicao)."""
    bruto = 0
    deslocamento = 0
    for _ in range(10):
        if pos >= len(dados):
            return None
        byte = dados[pos]
        pos += 1
        bruto |= (byte & 0x7F) << deslocamento
        if not byte & 0x80:
            return ((bruto >> 1) ^ -(bruto & 1), pos)
        deslocamento += 7
    return None


# -- remontagem de split --------------------------------------------------

class RemontadorSplit:
    """Junta os pedacos de uma mensagem grande do FishNet."""

    def __init__(self):
        self._pedacos: dict[tuple, dict[int, bytes]] = {}
        self._esperados: dict[tuple, int] = {}
        self._relogio = 0
        self._visto: dict[tuple, int] = {}

    def alimentar(self, conteudo: bytes, canal: int, sequencia: int | None) -> list[bytes]:
        """Devolve mensagens do FishNet prontas pra leitura.

        Conteudo que nao e split passa direto — a maioria dos pacotes.
        """
        if len(conteudo) < CABECALHO:
            return []
        if int.from_bytes(conteudo[4:6], "little") != PACOTE_SPLIT:
            return [conteudo]

        lido = _packed(conteudo, CABECALHO)
        if lido is None:
            return []
        quantos, pos = lido
        if quantos < 1 or quantos > PEDACOS_MAXIMOS:
            return []

        tick = int.from_bytes(conteudo[0:4], "little")
        chave = (canal, tick, quantos)
        self._relogio += 1
        self._visto[chave] = self._relogio

        pedacos = self._pedacos.setdefault(chave, {})
        self._esperados[chave] = quantos
        # a captura ve a ordem do fio, nao a da entrega: a sequencia do
        # LiteNetLib e o unico jeito de recolar na ordem certa
        ordem = sequencia if sequencia is not None else len(pedacos)
        pedacos[ordem] = conteudo[pos:]

        if sum(len(p) for p in pedacos.values()) > BYTES_MAXIMOS:
            self._descartar(chave)
            return []
        if len(pedacos) < quantos:
            self._podar()
            return []

        self._descartar(chave)
        return [b"".join(pedacos[k] for k in _ordem_circular(pedacos))]

    def _descartar(self, chave) -> None:
        self._pedacos.pop(chave, None)
        self._esperados.pop(chave, None)
        self._visto.pop(chave, None)

    def _podar(self) -> None:
        while len(self._pedacos) > SPLITS_SIMULTANEOS:
            self._descartar(min(self._visto, key=self._visto.get))


def _ordem_circular(pedacos: dict[int, bytes]) -> list[int]:
    """Ordena as sequencias sabendo que elas dao a volta em 65535."""
    chaves = sorted(pedacos)
    if chaves and max(chaves) - min(chaves) > 0x8000:
        return sorted(chaves, key=lambda k: k + 0x10000 if k < 0x8000 else k)
    return chaves


# -- a cacada -------------------------------------------------------------

def _inicio_plausivel(dados: bytes, i: int) -> bool:
    """Peneira barata antes de gastar um decodificador inteiro na posicao.

    CharacterData comeca com o marcador de objeto (0 = veio preenchido) e logo
    depois o UID, uma string curta e imprimivel. Quase todo lixo morre aqui.
    """
    if dados[i] != 0:
        return False
    if i + 2 > len(dados):
        return False
    bruto = dados[i + 1]
    if bruto & 0x80:                             # UID nunca precisa de 2 bytes
        return False
    tamanho = (bruto >> 1) ^ -(bruto & 1)
    if tamanho == -1:
        return True                              # UID nulo e possivel
    if tamanho < 1 or tamanho > TAMANHO_MAXIMO_UID:
        return False
    if i + 2 + tamanho > len(dados):
        return False
    return all(32 <= b < 127 for b in dados[i + 2:i + 2 + tamanho])


def cacar(dados: bytes, nome_esperado: str | None = None) -> list[Progresso]:
    """Todo CharacterData que couber neste conteudo."""
    achados: list[Progresso] = []
    limite = len(dados) - MINIMO_PLAUSIVEL
    for i in range(max(0, limite) + 1):
        if not _inicio_plausivel(dados, i):
            continue
        progresso = personagem.decodificar(dados[i:], com_tipo_de_update=False)
        if progresso is None:
            continue
        if nome_esperado is not None and progresso.nome != nome_esperado:
            continue
        if not _nome_aceitavel(progresso.nome):
            continue
        achados.append(progresso)
    return achados


def _nome_aceitavel(nome: str) -> bool:
    return bool(nome) and nome != "?" and all(c.isprintable() for c in nome)


class Cacador:
    """A cacada com memoria — e o que separa achado de coincidencia.

    Sozinho, um acerto e so "esses bytes couberam no formato". Mas o nome do
    personagem nao muda de um pacote pro outro: quando o mesmo nome aparece
    duas vezes, ele vira o esperado e dali em diante todo candidato com nome
    diferente e descartado sem cerimonia.
    """

    CONFIRMACOES = 2

    def __init__(self):
        self.nome: str | None = None
        self._contagem: dict[str, int] = {}

    def alimentar(self, dados: bytes) -> Progresso | None:
        """O progresso mais confiavel deste conteudo, se houver."""
        candidatos = cacar(dados, nome_esperado=self.nome)
        if not candidatos:
            return None

        if self.nome is not None:
            return candidatos[0]

        for candidato in candidatos:
            contagem = self._contagem.get(candidato.nome, 0) + 1
            self._contagem[candidato.nome] = contagem
            if contagem >= self.CONFIRMACOES:
                self.nome = candidato.nome
                self._contagem.clear()
                return candidato
        return None

    def esquecer(self) -> None:
        """Troca de personagem: o nome travado deixa de valer."""
        self.nome = None
        self._contagem.clear()
