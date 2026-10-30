"""Synchronous in-memory delivery of real messages to an elected client.

All members are available, leader=client 0, term=1. No sockets, packet loss,
election algorithm or failover are simulated. A round is committed only after
every vector and acknowledgement has been validated. The accepted experiment
fixes membership/leader; this is not a distributed consensus implementation.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter

import numpy as np

from .codec import (ACK, COMMIT, DELTA, DOWN, EMPTY, FULL, SETUP, UNKNOWN,
                    UP, DecodeError, Message, acknowledgement, check_ack,
                    decode_vector, encode_vector, validate_context)


class Traffic:
    def __init__(self) -> None:
        self.values: Counter = Counter()

    def add(self, packet: bytes, source: int, destination: int) -> None:
        if source == destination:
            raise ValueError("Leader-local work is not network traffic")
        msg = Message.from_bytes(packet)
        direction = "up" if destination == 0 else "down"
        category = "vector" if msg.kind in (UP, DOWN) else "control_setup"
        mode = {FULL: "full", DELTA: "delta", EMPTY: "unchanged"}[msg.mode]
        self.values[f"{direction}_bytes"] += len(packet)
        self.values[f"{category}_bytes"] += len(packet)
        self.values["total_bytes"] += len(packet)
        self.values["messages"] += 1
        if msg.kind in (UP, DOWN):
            self.values[f"{direction}_{mode}_messages"] += 1
            self.values[f"{direction}_vector_bytes"] += len(packet)

    def snapshot(self) -> dict:
        return dict(self.values)


class RelationProtocol:
    """Per-client committed relations make adaptive full replacement legal."""

    def __init__(self, edges: np.ndarray, samples: int, classes: int,
                 dimensions: tuple[int, ...], *, adaptive: bool):
        self.clients = len(dimensions)
        if not 2 <= self.clients <= 255:
            raise ValueError("This benchmark supports 2..255 clients")
        self.length = len(edges)
        self.adaptive = adaptive
        self.term = 1
        self.version = UNKNOWN
        self.graph_id = hashlib.sha256(edges.astype("<u4").tobytes()).digest()[:16]
        self.server_relations: list[np.ndarray | None] = [None] * self.clients
        self.client_relations: list[np.ndarray | None] = [None] * self.clients
        self.client_counts: list[np.ndarray | None] = [None] * self.clients
        self.counts: np.ndarray | None = None
        self.traffic = Traffic()
        # Graph and ID-order registration are sent once, rather than charging
        # only a graph hash. Raw public images/features are pre-provisioned.
        metadata = json.dumps({"samples": samples, "classes": classes,
                               "dimensions": dimensions, "edges": self.length,
                               "sample_id_order": "integer IDs 0..samples-1"},
                              sort_keys=True).encode("utf-8")
        graph_bytes = edges.astype("<u4").tobytes()
        body = len(metadata).to_bytes(4, "little") + metadata + graph_bytes
        setup = Message(SETUP, FULL, 0, self.term, UNKNOWN, UNKNOWN, 0,
                        self.length, self.length, self.graph_id, body).to_bytes()
        for client in range(1, self.clients):
            self.traffic.add(setup, 0, client)
            received = Message.from_bytes(setup)
            split = int.from_bytes(received.body[:4], "little")
            descriptor = json.loads(received.body[4:4 + split])
            graph = np.frombuffer(received.body[4 + split:], dtype="<u4").reshape(-1, 2)
            if (descriptor["edges"] != self.length
                    or not np.array_equal(graph, edges)
                    or hashlib.sha256(graph.tobytes()).digest()[:16] != self.graph_id):
                raise DecodeError("Graph registration failed")
            ack = acknowledgement(setup, client)
            self.traffic.add(ack, client, 0)
            check_ack(ack, setup, sender=client)

    def exchange(self, relations: list[np.ndarray]) -> dict:
        if len(relations) != self.clients:
            raise ValueError("A fixed-member round requires every client")
        base = self.version
        target = 0 if base == UNKNOWN else base + 1
        if target >= UNKNOWN:
            raise ValueError("Version range exhausted")
        before = self.traffic.snapshot()
        proposed: list[np.ndarray] = []
        # Receipt ACKs mean receipt, not commitment. All persistent references
        # remain untouched until the complete transaction has been checked.
        for client, relation in enumerate(relations):
            relation = np.asarray(relation)
            if relation.shape != (self.length,) or np.any(relation > 1) or np.any(relation < 0):
                raise ValueError("Invalid local hard relation")
            if client == 0:
                proposed.append(relation.astype(np.uint8, copy=True))
                continue
            packet = encode_vector(
                relation, self.client_relations[client], kind=UP,
                adaptive=self.adaptive, graph_id=self.graph_id, sender=client,
                base=base, target=target, maximum=1, term=self.term)
            self.traffic.add(packet, client, 0)
            decoded, _ = decode_vector(
                packet, self.server_relations[client], graph_id=self.graph_id,
                sender=client, base=base, target=target, length=self.length,
                maximum=1, kind=UP, term=self.term)
            proposed.append(decoded)
            ack = acknowledgement(packet, 0)
            self.traffic.add(ack, 0, client)
            check_ack(ack, packet, sender=0)

        if self.counts is None:
            staged_counts = np.sum(proposed, axis=0, dtype=np.int64)
        else:
            staged_counts = self.counts.astype(np.int64)
            for old, new in zip(self.server_relations, proposed):
                staged_counts += new.astype(np.int64) - old.astype(np.int64)
        if np.any(staged_counts < 0) or np.any(staged_counts > self.clients):
            raise ArithmeticError("Aggregate count outside membership bounds")
        staged_counts = staged_counts.astype(np.uint8)
        received_counts = [staged_counts.copy()]
        for client in range(1, self.clients):
            packet = encode_vector(
                staged_counts, self.counts, kind=DOWN, adaptive=self.adaptive,
                graph_id=self.graph_id, sender=0, base=base, target=target,
                maximum=self.clients, term=self.term)
            self.traffic.add(packet, 0, client)
            decoded, _ = decode_vector(
                packet, self.client_counts[client], graph_id=self.graph_id,
                sender=0, base=base, target=target, length=self.length,
                maximum=self.clients, kind=DOWN, term=self.term)
            received_counts.append(decoded)
            ready = acknowledgement(packet, client)
            self.traffic.add(ready, client, 0)
            check_ack(ready, packet, sender=client)

        # Bind commit to the exact aggregate. Delivery is synchronous/reliable;
        # crash recovery after partial delivery is explicitly out of scope.
        digest = hashlib.sha256(staged_counts.tobytes()).digest()[:16]
        commit = Message(COMMIT, EMPTY, 0, self.term, base, target, 0,
                         self.length, 0, self.graph_id, digest).to_bytes()
        for client in range(1, self.clients):
            self.traffic.add(commit, 0, client)
            received = Message.from_bytes(commit)
            validate_context(received, graph_id=self.graph_id, term=self.term,
                             base=base, target=target, sender=0, kind=COMMIT)
            if received.body != hashlib.sha256(received_counts[client].tobytes()).digest()[:16]:
                raise DecodeError("Commit digest mismatch")
            ack = acknowledgement(commit, client)
            self.traffic.add(ack, client, 0)
            check_ack(ack, commit, sender=client)

        self.server_relations = [r.copy() for r in proposed]
        self.client_relations = [r.copy() for r in relations]
        self.counts = staged_counts
        self.client_counts = received_counts
        self.version = target
        after = self.traffic.snapshot()
        return {key: after.get(key, 0) - before.get(key, 0) for key in after}

    def persistent_bytes(self) -> int:
        arrays = self.server_relations + self.client_relations + self.client_counts
        if self.counts is not None:
            arrays = arrays + [self.counts]
        seen = set()
        total = 0
        for arr in arrays:
            if arr is not None and id(arr) not in seen:
                seen.add(id(arr))
                total += arr.nbytes
        return total
