"""Reads FishNet's wire format — the serialization the game speaks over UDP.

A port of the primitives used by spirit-vale-tools (MIT). There are only a
few, and they are simple; the hard part is never the types, it's knowing the
ORDER of the fields inside a payload. That comes from the game's RPC catalog.

The central type is the "packed" integer: variable width with zigzag encoding,
the same scheme protobuf uses. Each byte carries 7 bits of value and the high
bit says whether another byte follows. Zigzag then restores the sign — which
is why -1 (used as "null" for strings and lists) fits in a single byte.
"""

from __future__ import annotations

import struct


class TruncatedPayload(Exception):
    """Ran out of bytes in the middle of a field."""


class InvalidPayload(Exception):
    """A value makes no sense for its field: absurd length, broken utf-8."""


class Reader:
    """Walks a payload field by field, in the order the game wrote them."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    # -- bounds -----------------------------------------------------------

    def _require(self, count: int) -> None:
        if self.pos + count > len(self.data):
            raise TruncatedPayload(
                f"out of bytes: asked for {count} at {self.pos}, "
                f"payload is {len(self.data)}")

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    # -- types ------------------------------------------------------------

    def boolean(self) -> bool:
        self._require(1)
        value = self.data[self.pos] == 1
        self.pos += 1
        return value

    def object_marker(self) -> bool:
        """One byte telling whether an object arrived null.

        Inverted on purpose: on the wire, 1 means "is null".
        """
        return not self.boolean()

    def packed(self) -> int:
        """Variable-width integer with zigzag encoding (same as protobuf)."""
        raw = 0
        shift = 0
        for _ in range(10):
            self._require(1)
            byte = self.data[self.pos]
            self.pos += 1
            raw |= (byte & 0x7F) << shift
            if not byte & 0x80:
                # zigzag: even values are positive, odd ones negative
                return (raw >> 1) ^ -(raw & 1)
            shift += 7
        raise InvalidPayload("packed integer never ended (over 10 bytes)")

    def text(self, max_length: int) -> str | None:
        """Length-prefixed utf-8 string. A length of -1 means null."""
        length = self.packed()
        if length == -1:
            return None
        if length < 0 or length > max_length:
            raise InvalidPayload(f"implausible string length: {length}")
        self._require(length)
        raw = self.data[self.pos:self.pos + length]
        self.pos += length
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InvalidPayload(f"string is not valid utf-8: {error}") from error

    def float_value(self) -> float:
        self._require(4)
        value = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return value

    def list_of(self, read_item) -> list:
        """Length-prefixed collection. A length of -1 means empty."""
        length = self.packed()
        if length == -1:
            return []
        if length < 0 or length > 100_000:
            raise InvalidPayload(f"implausible list length: {length}")
        return [read_item() for _ in range(length)]

    def booleans(self) -> list[bool]:
        return self.list_of(self.boolean)

    def dictionary(self, read_value) -> None:
        """Walks past a string-keyed dictionary, discarding the contents."""
        length = self.packed()
        if length == -1:
            return
        if length < 0 or length > 100_000:
            raise InvalidPayload(f"implausible dictionary length: {length}")
        for _ in range(length):
            self.text(256)
            read_value()

    # -- misc -------------------------------------------------------------

    def skip(self, count: int) -> None:
        self._require(count)
        self.pos += count
