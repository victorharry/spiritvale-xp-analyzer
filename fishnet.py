"""The FishNet layer — where we dig for the CharacterData.

Two things happen in this file.

**Split reassembly.** When a FishNet message does not fit in one packet it
goes out as a `split`: several chunks sharing a tick, numbered. CharacterData
is big enough to take that path often.

**The hunt.** Here I took a deliberate shortcut, and it is worth saying why.

Their full decoder resolves every RPC by name: it reads a four-thousand-line
RPC map, follows `objectSpawn` messages to learn which "link id" became which
method, and only then knows where a CharacterCallback_T payload begins. That
is the right approach if you want to read the whole protocol. We want ONE
field.

So instead of resolving the protocol, we try to decode CharacterData starting
at every plausible offset in the packet. What keeps that honest is the decoder
itself: to pass, a slice must contain six valid utf-8 strings within their
length limits, a UID shaped like a GUID, and end in a class level of 1..150
and a job level of 1..70. Garbage does not survive that funnel — and whatever
survives by accident still has to repeat the same character name to be taken
seriously (see `Hunter`).

The cost is the ceiling: if we ever need other fields, porting the real RPC
resolution becomes worth it.
"""

from __future__ import annotations

import character
from character import Progress

SPLIT_PACKET = 2
HEADER = 6                # 4 de tick + 2 de id do packet

MAX_CHUNKS = 1024
MAX_BYTES = 1024 * 1024
MAX_OPEN_SPLITS = 32

# size minimo pra valer a tentativa: dois UIDs, dois textos e o name ja
# passam disso com folga
MIN_PLAUSIBLE = 100
MAX_UID_LENGTH = 80


def _read_packed(data: bytes, pos: int) -> tuple[int, int] | None:
    """Reads a zigzag packed integer. Returns (value, next position)."""
    rawsocket = 0
    shift = 0
    for _ in range(10):
        if pos >= len(data):
            return None
        byte = data[pos]
        pos += 1
        rawsocket |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return ((rawsocket >> 1) ^ -(rawsocket & 1), pos)
        shift += 7
    return None


# -- remontagem de split --------------------------------------------------

class SplitReassembler:
    """Junta os chunks de uma message grande do FishNet."""

    def __init__(self):
        self._chunks: dict[tuple, dict[int, bytes]] = {}
        self._expected: dict[tuple, int] = {}
        self._clock = 0
        self._seen: dict[tuple, int] = {}

    def feed(self, payload: bytes, channel: int, sequence: int | None) -> list[bytes]:
        """Returns FishNet messages ready to be read.

        Anything that is not a split passes straight through, which is most
        packets.
        """
        if len(payload) < HEADER:
            return []
        if int.from_bytes(payload[4:6], "little") != SPLIT_PACKET:
            return [payload]

        lido = _read_packed(payload, HEADER)
        if lido is None:
            return []
        count, pos = lido
        if count < 1 or count > MAX_CHUNKS:
            return []

        tick = int.from_bytes(payload[0:4], "little")
        key = (channel, tick, count)
        self._clock += 1
        self._seen[key] = self._clock

        chunks = self._chunks.setdefault(key, {})
        self._expected[key] = count
        # capture sees wire order, not delivery order: the LiteNetLib
        # sequence is the only way to glue the chunks back correctly
        ordem = sequence if sequence is not None else len(chunks)
        chunks[ordem] = payload[pos:]

        if sum(len(p) for p in chunks.values()) > MAX_BYTES:
            self._drop(key)
            return []
        if len(chunks) < count:
            self._prune()
            return []

        self._drop(key)
        return [b"".join(chunks[k] for k in _wraparound_order(chunks))]

    def _drop(self, key) -> None:
        self._chunks.pop(key, None)
        self._expected.pop(key, None)
        self._seen.pop(key, None)

    def _prune(self) -> None:
        while len(self._chunks) > MAX_OPEN_SPLITS:
            self._drop(min(self._seen, key=self._seen.get))


def _wraparound_order(chunks: dict[int, bytes]) -> list[int]:
    """Ordena as sequencias sabendo que elas dao a volta em 65535."""
    keys = sorted(chunks)
    if keys and max(keys) - min(keys) > 0x8000:
        return sorted(keys, key=lambda k: k + 0x10000 if k < 0x8000 else k)
    return keys


# -- a cacada -------------------------------------------------------------

def _plausible_start(data: bytes, i: int) -> bool:
    """Peneira barata antes de gastar um decodificador inteiro na posicao.

    CharacterData comeca com o marcador de object_marker (0 = veio preenchido) e logo
    depois o UID, uma string curta e imprimivel. Quase todo lixo morre aqui.
    """
    if data[i] != 0:
        return False
    if i + 2 > len(data):
        return False
    rawsocket = data[i + 1]
    if rawsocket & 0x80:                             # UID nunca precisa de 2 bytes
        return False
    size = (rawsocket >> 1) ^ -(rawsocket & 1)
    if size == -1:
        return True                              # UID nulo e possivel
    if size < 1 or size > MAX_UID_LENGTH:
        return False
    if i + 2 + size > len(data):
        return False
    return all(32 <= b < 127 for b in data[i + 2:i + 2 + size])


def hunt(data: bytes, expected_name: str | None = None) -> list[Progress]:
    """Every CharacterData that fits in this payload."""
    found: list[Progress] = []
    limit = len(data) - MIN_PLAUSIBLE
    for i in range(max(0, limit) + 1):
        if not _plausible_start(data, i):
            continue
        progress = character.decode(data[i:], with_update_type=False,
                                           require_guid=True)
        if progress is None:
            continue
        if expected_name is not None and progress.name != expected_name:
            continue
        if not _name_is_sane(progress.name):
            continue
        found.append(progress)
    return found


def _name_is_sane(name: str) -> bool:
    if not name or name == "?" or not all(c.isprintable() for c in name):
        return False
    # a name shaped like a GUID means a shifted read, not a character
    return not character.GUID.match(name)


class Hunter:
    """The hunt, with memory — what separates a find from a coincidence.

    On its own, a hit only says "these bytes fit the format". But a character
    name does not change from one packet to the next: once the same name shows
    up twice it becomes the expected one, and from then on any candidate with
    a different name is dropped without ceremony.
    """

    CONFIRMATIONS = 2
    SWITCH_AFTER = 4

    def __init__(self):
        self.name: str | None = None
        self._tally: dict[str, int] = {}

    def feed(self, data: bytes) -> Progress | None:
        """O progress mais reliable deste payload, se houver."""
        candidates = hunt(data)
        if not candidates:
            return None

        for candidate in candidates:
            if candidate.name == self.name:
                return candidate

        # nenhum e o character travado. Pode ser so a list_of de personagens da
        # tela de selecao passando (cada um aparece uma ou duas vezes) ou uma
        # troca de verdade — por isso trocar custa mais confirmacoes do que
        # travar da primeira vez
        limit = self.SWITCH_AFTER if self.name is not None else self.CONFIRMATIONS
        for candidate in candidates:
            tally = self._tally.get(candidate.name, 0) + 1
            self._tally[candidate.name] = tally
            if tally >= limit:
                self.name = candidate.name
                self._tally.clear()
                return candidate
        return None

    def forget(self) -> None:
        """Character switch: the locked name stops being valid."""
        self.name = None
        self._tally.clear()
