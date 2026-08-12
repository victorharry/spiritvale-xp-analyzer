"""Unwraps IP and UDP — a raw packet becomes "this came from port N".

A lean port of the packet parser in spirit-vale-tools (MIT). Only what the
capture needs: drop anything that is not UDP and hand over the payload with
its ports.

One detail that looks like pedantry but is not: fragmented IP packets (offset
other than zero) are dropped. A middle fragment has no UDP header; read as if
it did, it becomes an invented datagram with random-looking ports.
"""

from __future__ import annotations

from dataclasses import dataclass

UDP_PROTOCOL = 17
IPV6_EXTENSIONS = (0, 43, 44, 51, 60)


@dataclass(frozen=True)
class Datagram:
    source_port: int
    dest_port: int
    data: bytes

    def involves(self, ports: set[int]) -> bool:
        return self.source_port in ports or self.dest_port in ports


def parse(packet: bytes) -> Datagram | None:
    if len(packet) < 20:
        return None
    version = packet[0] >> 4
    if version == 4:
        return _ipv4(packet)
    if version == 6:
        return _ipv6(packet)
    return None


def _ipv4(packet: bytes) -> Datagram | None:
    header_size = (packet[0] & 0x0F) * 4
    if header_size < 20 or header_size > len(packet):
        return None
    if packet[9] != UDP_PROTOCOL:
        return None
    fragment = int.from_bytes(packet[6:8], "big")
    if fragment & 0x1FFF:                      # not the first fragment
        return None
    declared = int.from_bytes(packet[2:4], "big")
    if declared < header_size:
        return None
    return _udp(packet, header_size, min(declared, len(packet)))


def _ipv6(packet: bytes) -> Datagram | None:
    if len(packet) < 40:
        return None
    declared = 40 + int.from_bytes(packet[4:6], "big")
    end = min(declared, len(packet))
    next_header = packet[6]
    pos = 40
    while next_header in IPV6_EXTENSIONS:
        if pos + 2 > end:
            return None
        current, next_header = next_header, packet[pos]
        if current == 44:                      # fragment header
            return None
        size = ((packet[pos + 1] + 2) * 4 if current == 51
                else (packet[pos + 1] + 1) * 8)
        pos += size
        if pos > end:
            return None
    if next_header != UDP_PROTOCOL:
        return None
    return _udp(packet, pos, end)


def _udp(packet: bytes, start: int, end: int) -> Datagram | None:
    if start + 8 > end:
        return None
    length = int.from_bytes(packet[start + 4:start + 6], "big")
    if length < 8:
        return None
    last = min(start + length, end)
    return Datagram(
        source_port=int.from_bytes(packet[start:start + 2], "big"),
        dest_port=int.from_bytes(packet[start + 2:start + 4], "big"),
        data=packet[start + 8:last],
    )
