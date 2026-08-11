"""Camada LiteNetLib — o envelope que o jogo usa dentro do UDP.

Porte das partes que interessam do spirit-vale-tools (MIT). Sao tres formatos
empilhados e a gente precisa dos tres pra chegar no conteudo:

    UDP -> LiteNetLib -> FishNet -> CharacterData

O LiteNetLib faz duas coisas que quebram um leitor ingenuo:

  * **merge** — varias mensagens pequenas viajam num datagrama so, cada uma
    precedida do proprio tamanho. Ler so a primeira perde o resto.
  * **fragmento** — uma mensagem grande e picada em varios datagramas. E
    exatamente o caso do CharacterData, que e gordo. Sem remontar, a gente ve
    metade do personagem e nunca decodifica nada.

Aqui nada levanta excecao por pacote estranho: captura passiva ve barulho, ve
retransmissao, ve pacote cortado. O jeito certo de reagir e ignorar aquele
pacote, nao derrubar a leitura.
"""

from __future__ import annotations

from dataclasses import dataclass

MASCARA_TIPO = 0x1F
MASCARA_FRAGMENTADO = 0x80
TIPO_UNIDO = 12
PROFUNDIDADE_MAXIMA = 8

NOMES = ("unreliable", "channeled", "ack", "ping", "pong", "connectRequest",
         "connectAccept", "disconnect", "unconnectedMessage", "mtuCheck",
         "mtuOk", "broadcast", "merged", "shutdownOk", "peerNotFound",
         "invalidProtocol", "natMessage", "empty")

# um fragmento incompleto nao pode ficar preso pra sempre
FRAGMENTOS_MAXIMOS = 64
PARTES_MAXIMAS = 1024
BYTES_MAXIMOS = 4 * 1024 * 1024


@dataclass(frozen=True)
class Pacote:
    tipo: str
    canal: int | None
    sequencia: int | None
    fragmento: tuple[int, int, int] | None   # (id, parte, total)
    dados: bytes

    @property
    def confiavel(self) -> bool:
        return self.tipo == "channeled"

    @property
    def carrega_conteudo(self) -> bool:
        return self.tipo in ("unreliable", "channeled")


def decodificar(datagrama: bytes) -> list[Pacote]:
    """Todos os pacotes de um datagrama, ja abrindo os merges."""
    saida: list[Pacote] = []
    _ler(datagrama, 0, saida)
    return saida


def _ler(dados: bytes, profundidade: int, saida: list[Pacote]) -> None:
    if not dados or profundidade > PROFUNDIDADE_MAXIMA:
        return
    tipo_id = dados[0] & MASCARA_TIPO
    if tipo_id >= len(NOMES):
        return
    if tipo_id == TIPO_UNIDO:
        _ler_unido(dados, profundidade, saida)
        return
    pacote = _folha(dados, tipo_id)
    if pacote is not None:
        saida.append(pacote)


def _ler_unido(dados: bytes, profundidade: int, saida: list[Pacote]) -> None:
    pos = 1
    while pos + 2 <= len(dados):
        tamanho = int.from_bytes(dados[pos:pos + 2], "little")
        pos += 2
        if tamanho == 0 or pos + tamanho > len(dados):
            return
        _ler(dados[pos:pos + tamanho], profundidade + 1, saida)
        pos += tamanho


def _folha(dados: bytes, tipo_id: int) -> Pacote | None:
    fragmentado = bool(dados[0] & MASCARA_FRAGMENTADO)
    nome = NOMES[tipo_id]

    if tipo_id == 0:
        return Pacote(nome, None, None, None, dados[1:])

    if tipo_id == 1:
        cabecalho = 10 if fragmentado else 4
        if len(dados) < cabecalho:
            return None
        fragmento = None
        if fragmentado:
            fragmento = (int.from_bytes(dados[4:6], "little"),
                         int.from_bytes(dados[6:8], "little"),
                         int.from_bytes(dados[8:10], "little"))
        return Pacote(nome, dados[3],
                      int.from_bytes(dados[1:3], "little"),
                      fragmento, dados[cabecalho:])

    # ack, ping, pong e os de controle nao carregam conteudo de jogo
    return Pacote(nome, None, None, None, b"")


class Remontador:
    """Junta os fragmentos e entrega mensagens LiteNetLib inteiras.

    Guarda por (canal, id do fragmento). Assim que todas as partes chegam,
    devolve o conteudo colado; enquanto nao chegam, devolve nada.
    """

    def __init__(self):
        self._pendentes: dict[tuple[int, int], dict[int, bytes]] = {}
        self._totais: dict[tuple[int, int], int] = {}
        self._relogio = 0
        self._visto: dict[tuple[int, int], int] = {}

    def alimentar(self, pacote: Pacote) -> list[bytes]:
        """Devolve as mensagens completas que este pacote destravou."""
        if not pacote.carrega_conteudo:
            return []
        if pacote.fragmento is None:
            return [pacote.dados] if pacote.dados else []

        identificador, parte, total = pacote.fragmento
        if total < 1 or total > PARTES_MAXIMAS or parte >= total:
            return []

        chave = (pacote.canal or 0, identificador)
        self._relogio += 1
        self._visto[chave] = self._relogio
        partes = self._pendentes.setdefault(chave, {})
        self._totais[chave] = total
        partes[parte] = pacote.dados

        if sum(len(p) for p in partes.values()) > BYTES_MAXIMOS:
            self._descartar(chave)
            return []
        if len(partes) < total:
            self._podar()
            return []

        self._descartar(chave)
        return [b"".join(partes[i] for i in range(total))]

    def _descartar(self, chave) -> None:
        self._pendentes.pop(chave, None)
        self._totais.pop(chave, None)
        self._visto.pop(chave, None)

    def _podar(self) -> None:
        """Fragmento cujo resto se perdeu na rede nunca completa; o mais antigo
        sai pra memoria nao crescer sozinha."""
        while len(self._pendentes) > FRAGMENTOS_MAXIMOS:
            mais_velho = min(self._visto, key=self._visto.get)
            self._descartar(mais_velho)
