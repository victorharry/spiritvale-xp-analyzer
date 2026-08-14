"""Decodes ExpCoinsChanged_T, the packet that carries the player's gold.

The server sends this whenever experience or coins change, which in practice
means on every kill. It is five packed integers and nothing else:

    exp, level, jobExp, jobLevel, coins

That shape is the whole problem. CharacterData can be found by brute force
because it has to contain six valid utf-8 strings and a GUID before it is
believed (see character.py); five bare integers have no such structure, so any
run of digits anywhere in any packet would "decode" and hand back a convincing
wrong number.

What replaces that structure is a cross-check the program already has for
free: the level and job level, which arrived earlier in CharacterData. A
candidate that disagrees with them is not this packet. Together with the
requirement that the five fields consume the payload to its last byte, that was
enough to pull 265 clean readings out of a three-minute capture with no absurd
value among them.

The field order comes from the RPC catalog mapped by spirit-vale-tools (MIT):
wireHash 41, targetRpc, on the player-save economy component.
"""

from __future__ import annotations

from dataclasses import dataclass

# ceilings used as sanity checks, not as game rules. A value past these means
# the read drifted, not that the player is rich.
MAX_XP = 10_000_000_000
MAX_COINS = 1_000_000_000_000

FIELDS = 5
MIN_PAYLOAD = FIELDS            # one byte per field, at the very least


@dataclass(frozen=True)
class Wallet:
    """One ExpCoinsChanged_T reading."""

    xp: int
    level: int
    job_xp: int
    job_level: int
    coins: int


def _packed(data: bytes, pos: int) -> tuple[int, int] | None:
    """Reads a zigzag packed integer. Returns (value, next position)."""
    raw = 0
    shift = 0
    for _ in range(10):
        if pos >= len(data):
            return None
        byte = data[pos]
        pos += 1
        raw |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return ((raw >> 1) ^ -(raw & 1), pos)
        shift += 7
    return None


def decode(payload: bytes, level: int, job_level: int) -> Wallet | None:
    """Finds the reading inside a FishNet payload, or None if it is not there.

    Walks every offset and keeps the FIRST that fits. First, not any, and the
    difference matters: starting one byte into a multi-byte integer reads the
    tail of that same integer as a smaller number and lands on the same byte as
    the real read, so the four fields after it come out identical. Those near
    misses agree on the coins and disagree on the xp, and only the earliest
    offset has the xp right.
    """
    if len(payload) < MIN_PAYLOAD:
        return None
    for start in range(len(payload) - MIN_PAYLOAD + 1):
        pos = start
        values = []
        for _ in range(FIELDS):
            read = _packed(payload, pos)
            if read is None:
                break
            values.append(read[0])
            pos = read[1]
        if len(values) != FIELDS:
            continue
        if pos != len(payload):
            # the packet has to end here. Without this the scan finds the five
            # fields buried in the middle of unrelated traffic
            continue
        xp, lvl, job_xp, job_lvl, coins = values
        if lvl != level or job_lvl != job_level:
            continue
        if not (0 <= xp <= MAX_XP and 0 <= job_xp <= MAX_XP):
            continue
        if not (0 <= coins <= MAX_COINS):
            continue
        return Wallet(xp=xp, level=lvl, job_xp=job_xp,
                      job_level=job_lvl, coins=coins)
    return None
