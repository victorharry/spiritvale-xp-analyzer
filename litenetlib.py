"""The LiteNetLib layer — the envelope the game uses inside UDP.

A port of the parts that matter from spirit-vale-tools (MIT). Three formats
are stacked and all three have to be unwrapped to reach the payload:

    UDP -> LiteNetLib -> FishNet -> CharacterData

LiteNetLib does two things that break a naive reader:

  * **merge** — several small messages travel in one datagram, each prefixed
    with its own size. Reading only the first one loses the rest.
  * **fragment** — a large message is sliced across several datagrams. That is
    exactly what happens to CharacterData, which is fat. Without reassembly
    you see half a character and never decode anything.

Nothing here raises on a strange packet. Passive capture sees noise, sees
retransmissions, sees truncated frames. The right reaction is to ignore that
packet, not to bring the reading down.
"""

from __future__ import annotations

from dataclasses import dataclass

KIND_MASK = 0x1F
FRAGMENTED_MASK = 0x80
MERGED_KIND = 12
MAX_DEPTH = 8

KIND_NAMES = ("unreliable", "channeled", "ack", "ping", "pong", "connectRequest",
         "connectAccept", "disconnect", "unconnectedMessage", "mtuCheck",
         "mtuOk", "broadcast", "merged", "shutdownOk", "peerNotFound",
         "invalidProtocol", "natMessage", "empty")

# an incomplete fragment must not be held forever
MAX_PENDING_FRAGMENTS = 64
MAX_PARTS = 1024
MAX_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True)
class Packet:
    kind: str
    channel: int | None
    sequence: int | None
    fragment: tuple[int, int, int] | None   # (id, part, total)
    data: bytes

    @property
    def reliable(self) -> bool:
        return self.kind == "channeled"

    @property
    def carries_payload(self) -> bool:
        return self.kind in ("unreliable", "channeled")


def decode(datagram: bytes) -> list[Packet]:
    """Every packet in a datagram, with merges already opened up."""
    out: list[Packet] = []
    _read(datagram, 0, out)
    return out


def _read(data: bytes, depth: int, out: list[Packet]) -> None:
    if not data or depth > MAX_DEPTH:
        return
    kind_id = data[0] & KIND_MASK
    if kind_id >= len(KIND_NAMES):
        return
    if kind_id == MERGED_KIND:
        _read_merged(data, depth, out)
        return
    packet = _leaf(data, kind_id)
    if packet is not None:
        out.append(packet)


def _read_merged(data: bytes, depth: int, out: list[Packet]) -> None:
    pos = 1
    while pos + 2 <= len(data):
        size = int.from_bytes(data[pos:pos + 2], "little")
        pos += 2
        if size == 0 or pos + size > len(data):
            return
        _read(data[pos:pos + size], depth + 1, out)
        pos += size


def _leaf(data: bytes, kind_id: int) -> Packet | None:
    fragmented = bool(data[0] & FRAGMENTED_MASK)
    name = KIND_NAMES[kind_id]

    if kind_id == 0:
        return Packet(name, None, None, None, data[1:])

    if kind_id == 1:
        header = 10 if fragmented else 4
        if len(data) < header:
            return None
        fragment = None
        if fragmented:
            fragment = (int.from_bytes(data[4:6], "little"),
                         int.from_bytes(data[6:8], "little"),
                         int.from_bytes(data[8:10], "little"))
        return Packet(name, data[3],
                      int.from_bytes(data[1:3], "little"),
                      fragment, data[header:])

    # ack, ping, pong and the control kinds carry no game payload
    return Packet(name, None, None, None, b"")


class Reassembler:
    """Joins fragments back into whole LiteNetLib messages.

    Keyed by (channel, fragment id). Once every part has arrived it returns
    the pieces glued together; until then it returns nothing.
    """

    def __init__(self):
        self._pending: dict[tuple[int, int], dict[int, bytes]] = {}
        self._totals: dict[tuple[int, int], int] = {}
        self._clock = 0
        self._seen: dict[tuple[int, int], int] = {}

    def feed(self, packet: Packet) -> list[bytes]:
        """The complete messages this packet unlocked, if any."""
        if not packet.carries_payload:
            return []
        if packet.fragment is None:
            return [packet.data] if packet.data else []

        ident, part, total = packet.fragment
        if total < 1 or total > MAX_PARTS or part >= total:
            return []

        key = (packet.channel or 0, ident)
        self._clock += 1
        self._seen[key] = self._clock
        parts = self._pending.setdefault(key, {})
        self._totals[key] = total
        parts[part] = packet.data

        if sum(len(p) for p in parts.values()) > MAX_BYTES:
            self._drop(key)
            return []
        if len(parts) < total:
            self._prune()
            return []

        self._drop(key)
        return [b"".join(parts[i] for i in range(total))]

    def _drop(self, key) -> None:
        self._pending.pop(key, None)
        self._totals.pop(key, None)
        self._seen.pop(key, None)

    def _prune(self) -> None:
        """A fragment whose siblings were lost on the wire never completes,
        so the oldest one is dropped to keep memory from growing on its own."""
        while len(self._pending) > MAX_PENDING_FRAGMENTS:
            oldest = min(self._seen, key=self._seen.get)
            self._drop(oldest)
