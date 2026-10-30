"""Real bit-packed full/delta messages, strict decoding, versioned ACKs.

Uploads: changed edge IDs + one direction bit (1 = 0->1, 0 = 1->0).
Downloads: changed edge IDs + new integer counts. Both endpoints keep the
committed reference; the aggregator retains each client's previous relation,
so a per-client full replacement is a valid operation. That memory is counted.
"""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass

import numpy as np

UP, DOWN, ACK, COMMIT, SETUP = range(1, 6)
FULL, DELTA, EMPTY = range(1, 4)
UNKNOWN = 0xFFFFFFFF
HEADER = struct.Struct("<4sBBBBIIIIII16s")
MAGIC = b"FRC1"


class DecodeError(ValueError):
    pass


def value_bits(maximum: int) -> int:
    return max(1, int(maximum).bit_length())


def pack_values(values: np.ndarray, bits: int) -> bytes:
    values = np.asarray(values)
    if not 1 <= bits <= 32 or np.any(values < 0) or np.any(values >= 1 << bits):
        raise ValueError("Value does not fit packed representation")
    if not len(values):
        return b""
    raw = ((values.astype(np.uint64)[:, None]
            >> np.arange(bits, dtype=np.uint64)) & 1).astype(np.uint8)
    return np.packbits(raw.ravel(), bitorder="little").tobytes()


def unpack_values(data: bytes, count: int, bits: int) -> np.ndarray:
    if not 1 <= bits <= 32 or count < 0:
        raise DecodeError("Invalid packed array shape")
    if len(data) != (count * bits + 7) // 8:
        raise DecodeError("Packed length mismatch")
    raw = np.unpackbits(np.frombuffer(data, dtype=np.uint8), bitorder="little")
    if np.any(raw[count * bits:]):
        raise DecodeError("Nonzero padding bits")
    if not count:
        return np.empty(0, dtype=np.uint32)
    raw = raw[:count * bits].reshape(count, bits).astype(np.uint64)
    values = (raw * (np.uint64(1) << np.arange(bits, dtype=np.uint64))).sum(axis=1)
    return values.astype(np.uint32)


@dataclass(frozen=True)
class Message:
    kind: int
    mode: int
    bits: int
    term: int
    base: int
    target: int
    sender: int
    length: int
    items: int
    graph_id: bytes
    body: bytes = b""

    def to_bytes(self) -> bytes:
        return HEADER.pack(MAGIC, 1, self.kind, self.mode, self.bits,
                           self.term, self.base, self.target, self.sender,
                           self.length, self.items, self.graph_id) + self.body

    @classmethod
    def from_bytes(cls, packet: bytes) -> "Message":
        if len(packet) < HEADER.size:
            raise DecodeError("Truncated header")
        fields = HEADER.unpack(packet[:HEADER.size])
        if fields[0] != MAGIC or fields[1] != 1:
            raise DecodeError("Unknown wire format")
        _, _, kind, mode, bits, term, base, target, sender, length, items, graph_id = fields
        if kind not in (UP, DOWN, ACK, COMMIT, SETUP):
            raise DecodeError("Unknown message kind")
        if mode not in (FULL, DELTA, EMPTY):
            raise DecodeError("Unknown coding mode")
        return cls(kind, mode, bits, term, base, target, sender,
                   length, items, graph_id, packet[HEADER.size:])


def validate_context(msg: Message, *, graph_id: bytes, term: int, base: int,
                     target: int, sender: int, kind: int) -> None:
    actual = (msg.graph_id, msg.term, msg.base, msg.target, msg.sender, msg.kind)
    expected = (graph_id, term, base, target, sender, kind)
    if actual != expected:
        raise DecodeError("Wrong graph, term, version, sender or message kind")


def encode_vector(current: np.ndarray, previous: np.ndarray | None, *,
                  kind: int, adaptive: bool, graph_id: bytes, sender: int,
                  base: int, target: int, maximum: int, term: int = 1) -> bytes:
    current = np.asarray(current)
    if kind not in (UP, DOWN) or current.ndim != 1:
        raise ValueError("Expected an upload/download vector")
    if np.any(current < 0) or np.any(current > maximum):
        raise ValueError("Vector outside allowed range")
    if (previous is None) != (base == UNKNOWN):
        raise ValueError("Missing or inconsistent committed base")
    if previous is not None and previous.shape != current.shape:
        raise ValueError("Reference shape mismatch")
    bits = value_bits(maximum)
    full = Message(kind, FULL, bits, term, base, target, sender,
                   len(current), len(current), graph_id,
                   pack_values(current, bits)).to_bytes()
    if not adaptive or previous is None:
        return full
    ids = np.flatnonzero(current != previous).astype(np.uint32)
    if not len(ids):
        return Message(kind, EMPTY, bits, term, base, target, sender,
                       len(current), 0, graph_id).to_bytes()
    id_bits = value_bits(max(0, len(current) - 1))
    body = pack_values(ids, id_bits) + pack_values(current[ids], bits)
    delta = Message(kind, DELTA, bits, term, base, target, sender,
                    len(current), len(ids), graph_id, body).to_bytes()
    return delta if len(delta) < len(full) else full


def decode_vector(packet: bytes, previous: np.ndarray | None, *,
                  graph_id: bytes, sender: int, base: int, target: int,
                  length: int, maximum: int, kind: int, term: int = 1
                  ) -> tuple[np.ndarray, Message]:
    msg = Message.from_bytes(packet)
    validate_context(msg, graph_id=graph_id, term=term, base=base,
                     target=target, sender=sender, kind=kind)
    if msg.length != length or msg.bits != value_bits(maximum):
        raise DecodeError("Wrong vector dimension or value width")
    if msg.items > length:
        raise DecodeError("Too many records")
    if (previous is None) != (base == UNKNOWN):
        raise DecodeError("Receiver lacks the acknowledged reference")
    if previous is not None and previous.shape != (length,):
        raise DecodeError("Receiver reference shape mismatch")
    if msg.mode == FULL:
        if msg.items != length:
            raise DecodeError("Incomplete full vector")
        current = unpack_values(msg.body, length, msg.bits)
    elif msg.mode == EMPTY:
        if previous is None or msg.items or msg.body:
            raise DecodeError("Invalid unchanged confirmation")
        current = previous.astype(np.uint32, copy=True)
    else:
        if previous is None or not msg.items:
            raise DecodeError("Delta without a committed base")
        id_bits = value_bits(max(0, length - 1))
        split = (msg.items * id_bits + 7) // 8
        ids = unpack_values(msg.body[:split], msg.items, id_bits)
        values = unpack_values(msg.body[split:], msg.items, msg.bits)
        if np.any(ids >= length) or np.any(ids[1:] <= ids[:-1]):
            raise DecodeError("Unsorted, repeated or out-of-range edge IDs")
        if np.any(previous[ids] == values):
            raise DecodeError("Delta includes a non-change or invalid direction")
        current = previous.astype(np.uint32, copy=True)
        current[ids] = values
    if np.any(current > maximum):
        raise DecodeError("Decoded vector outside allowed range")
    return current.astype(np.uint8 if maximum <= 255 else np.uint32), msg


def acknowledgement(packet: bytes, sender: int) -> bytes:
    original = Message.from_bytes(packet)
    return Message(ACK, EMPTY, 0, original.term, original.base, original.target,
                   sender, original.length, 0, original.graph_id,
                   hashlib.sha256(packet).digest()[:16]).to_bytes()


def check_ack(packet: bytes, original: bytes, *, sender: int) -> None:
    msg, source = Message.from_bytes(packet), Message.from_bytes(original)
    validate_context(msg, graph_id=source.graph_id, term=source.term,
                     base=source.base, target=source.target, sender=sender, kind=ACK)
    if (msg.mode != EMPTY or msg.bits or msg.items or msg.length != source.length
            or msg.body != hashlib.sha256(original).digest()[:16]):
        raise DecodeError("ACK does not identify the accepted message")
