"""Actual serialized request, union, vote and target messages on the fixed graph."""

from collections import Counter
import hashlib

import numpy as np

from experiments.public_scaling.codec import (
    COMMIT, DOWN, EMPTY, FULL, SETUP, UNKNOWN, UP, Message, acknowledgement,
    check_ack, decode_vector, encode_vector, pack_values, unpack_values,
    validate_context, value_bits,
)
from experiments.public_scaling.protocol import RelationProtocol
from experiments.snapshot_certification_timing.design import require


class DemandProtocol(RelationProtocol):
    """Reuse graph registration; commit only the counts requested this round."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.breakdown = Counter()

    def transmit(self, packet, src, dst, category):
        self.traffic.add(packet, src, dst)
        self.breakdown[category] += len(packet)
        return packet

    def control(self, values, bits, channel, src, dst, target, count, category):
        msg = Message(SETUP, FULL, bits, self.term, self.version, target, src,
                      self.length, count, self.graph_id, channel + pack_values(values, bits))
        received = Message.from_bytes(self.transmit(msg.to_bytes(), src, dst, category))
        validate_context(received, graph_id=self.graph_id, term=self.term, base=self.version,
                         target=target, sender=src, kind=SETUP)
        require((received.mode, received.bits, received.length, received.items, received.body[:1])
                == (FULL, bits, self.length, count, channel), 'Invalid request or union envelope')
        return unpack_values(received.body[1:], count, bits)

    def needs(self, orders, target):
        require(len(orders) == self.clients and all(len(order) == len(orders[0]) for order in orders),
                'Invalid student request batch')
        leader_orders = [orders[0]]
        width = value_bits(self.length-1)
        for i, order in enumerate(orders[1:], 1):
            received = self.control(order, width, b'R', i, 0, target, len(order), 'request_up_bytes')
            require(np.all(received < self.length) and len(np.unique(received)) == len(received),
                    'Invalid requested edge indices')
            leader_orders.append(received)
        union = np.unique(np.concatenate(leader_orders))
        mask = np.zeros(self.length, dtype=np.uint8)
        mask[union] = 1
        teacher_edges = [union]
        for i in range(1, self.clients):
            decoded = self.control(mask, 1, b'U', 0, i, target, self.length, 'union_down_bytes')
            teacher_edges.append(np.flatnonzero(decoded))
        return union, leader_orders, teacher_edges

    def vector(self, values, src, dst, kind, target, maximum, category):
        packet = encode_vector(values, None, kind=kind, adaptive=False, graph_id=self.graph_id,
                               sender=src, base=UNKNOWN, target=target, maximum=maximum, term=self.term)
        received = self.transmit(packet, src, dst, category)
        decoded, _ = decode_vector(received, None, graph_id=self.graph_id, sender=src, base=UNKNOWN,
                                   target=target, length=len(values), maximum=maximum, kind=kind, term=self.term)
        self.ack(packet, dst, src)
        return decoded

    def ack(self, packet, src, dst):
        ack = self.transmit(acknowledgement(packet, src), src, dst, 'ack_bytes')
        check_ack(ack, packet, sender=src)

    def exchange_demand(self, votes, union, leader_orders, target):
        require(len(votes) == self.clients and all(v.shape == union.shape for v in votes), 'Invalid union votes')
        received = [votes[0]]
        received.extend(self.vector(vote, i, 0, UP, target, 1, 'vote_up_bytes')
                        for i, vote in enumerate(votes[1:], 1))
        counts = np.sum(received, axis=0, dtype=np.uint8)
        expected = [counts[np.searchsorted(union, ids)] for ids in leader_orders]
        local = [expected[0]]
        local.extend(self.vector(values, 0, i, DOWN, target, self.clients, 'target_down_bytes')
                     for i, values in enumerate(expected[1:], 1))
        for i, values in enumerate(expected[1:], 1):
            checksum = hashlib.sha256(values.tobytes()).digest()[:16]
            msg = Message(COMMIT, EMPTY, 0, self.term, self.version, target, 0,
                          len(values), 0, self.graph_id, checksum).to_bytes()
            commit = Message.from_bytes(self.transmit(msg, 0, i, 'commit_down_bytes'))
            validate_context(commit, graph_id=self.graph_id, term=self.term, base=self.version,
                             target=target, sender=0, kind=COMMIT)
            require(commit.body == hashlib.sha256(local[i].tobytes()).digest()[:16], 'Wrong committed targets')
            self.ack(msg, i, 0)
        self.version = target
        return counts, local
