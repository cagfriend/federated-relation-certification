"""Demand with independently reconstructed schedules on a registered session."""

from dataclasses import dataclass
import json
from time import perf_counter
from types import SimpleNamespace

import numpy as np

from experiments.public_budget.student import selected_edges
from experiments.public_scaling.codec import (
    FULL, SETUP, UNKNOWN, DecodeError, Message, acknowledgement, check_ack, validate_context,
)
from experiments.snapshot_certification_timing.design import require
from ..on_demand.protocol import DemandProtocol

SAMPLER = 'numpy-default_rng-PCG64-seed-sequence-402-fixed-prefix-v1'
CHANNEL = b'S'


@dataclass(frozen=True)
class Schedule:
    seed: int
    samples: int
    degree: int
    steps: int
    batch: int
    members: int
    public_ids_sha256: str

    def body(self):
        return CHANNEL + json.dumps(dict(**vars(self), sampler=SAMPLER, numpy=np.__version__),
                                    sort_keys=True, separators=(',', ':')).encode('ascii')

    def spec(self):
        return SimpleNamespace(policy='fixed', steps=self.steps, config=SimpleNamespace(
            samples=self.samples, degree=self.degree, public_edge_batch=self.batch))


class SharedScheduleProtocol(DemandProtocol):
    """Only local orders cross into each participant's reconstruction."""

    def __init__(self, edges, samples, classes, dimensions, *, adaptive, schedule, audit_rows=None):
        super().__init__(edges, samples, classes, dimensions, adaptive=adaptive)
        require(schedule.samples == samples and schedule.members == self.clients
                and schedule.samples*schedule.degree//2 == self.length and schedule.steps > 0 and schedule.batch > 0,
                'Schedule size, membership or budget differs from the graph')
        self.audit_rows = audit_rows
        payload = schedule.body()
        packet = Message(SETUP, FULL, 0, self.term, UNKNOWN, UNKNOWN, 0,
                         self.length, self.clients, self.graph_id, payload).to_bytes()
        self.schedules = [schedule]
        for client in range(1, self.clients):
            received = self.register_packet(packet, client)
            self.schedules.append(self.accept_schedule(received, schedule))
            ack = acknowledgement(received, client)
            self.traffic.add(ack, client, 0)
            check_ack(ack, packet, sender=client)
        self.specs = [local.spec() for local in self.schedules]

    def register_packet(self, packet, client):
        self.traffic.add(packet, 0, client)
        return packet

    def accept_schedule(self, packet, expected):
        msg = Message.from_bytes(packet)
        validate_context(msg, graph_id=self.graph_id, term=self.term,
                         base=UNKNOWN, target=UNKNOWN, sender=0, kind=SETUP)
        if (msg.mode, msg.bits, msg.length, msg.items, msg.body[:1]) != (
                FULL, 0, self.length, self.clients, CHANNEL):
            raise DecodeError('Wrong schedule registration envelope')
        try:
            descriptor = json.loads(msg.body[1:])
            schedule = Schedule(**{key: descriptor[key] for key in vars(expected)})
        except (KeyError, TypeError, ValueError, UnicodeError) as exc:
            raise DecodeError('Malformed schedule registration') from exc
        if msg.body != expected.body() or schedule != expected:
            raise DecodeError('Wrong public IDs, sampler or schedule parameters')
        return schedule

    def needs(self, orders, target):
        expected = 0 if self.version == UNKNOWN else self.version+1
        width = min(self.length, self.schedules[0].steps*self.schedules[0].batch)
        require(target == expected and len(orders) == self.clients and all(o.shape == (width,) for o in orders),
                'Wrong round or locally generated student orders')
        # The explicit leader combines its native order with decoded uint32
        # orders. Match that promotion so both paths also hash the same bytes.
        union_dtype = np.result_type(orders[0].dtype, np.uint32)

        teacher_edges = []
        leader_orders = None
        for owner, (schedule, spec) in enumerate(zip(self.schedules, self.specs, strict=True)):
            start = perf_counter() if self.audit_rows is not None else None
            # The engine already ran each student's own sampler using the common seed.
            # Reuse only the owner's own order. All peer requests are reconstructed here.
            local_orders = [orders[owner] if member == owner else
                            selected_edges(spec, schedule.seed, member, target+1)
                            for member in range(schedule.members)]
            union = np.unique(np.concatenate(local_orders, dtype=union_dtype))
            if self.audit_rows is not None:
                self.audit_rows.append(dict(round=target+1, client=owner, seconds=perf_counter()-start,
                                            peer_orders=schedule.members-1, edges=len(union)))
                require(all(np.array_equal(a, b) for a, b in zip(local_orders, orders, strict=True))
                        and (not teacher_edges or np.array_equal(union, teacher_edges[0])),
                        f'Round {target+1}, client {owner}: reconstructed order or union differs')
            if owner == 0:
                leader_orders = local_orders
            teacher_edges.append(union)
        return teacher_edges[0], leader_orders, teacher_edges
