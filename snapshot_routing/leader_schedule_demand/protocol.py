"""Demand where the leader reconstructs peer requests and sends the usual union."""

from time import perf_counter

import numpy as np

from experiments.public_budget.student import selected_edges
from experiments.public_scaling.codec import UNKNOWN
from experiments.snapshot_certification_timing.design import require
from ..shared_schedule_demand.protocol import SharedScheduleProtocol


class LeaderScheduleProtocol(SharedScheduleProtocol):
    def needs(self, orders, target):
        expected = 0 if self.version == UNKNOWN else self.version+1
        schedule, spec = self.schedules[0], self.specs[0]
        budget = min(self.length, schedule.steps*schedule.batch)
        require(target == expected and len(orders) == self.clients and orders[0].shape == (budget,),
                'Wrong round or local student order')

        start = perf_counter() if self.audit_rows is not None else None
        leader_orders = [orders[0], *(selected_edges(spec, schedule.seed, peer, target+1)
                                     for peer in range(1, self.clients))]
        # Match the explicit protocol's combination of native and decoded uint32 orders.
        union = np.unique(np.concatenate(leader_orders, dtype=np.result_type(orders[0].dtype, np.uint32)))
        if self.audit_rows is not None:
            self.audit_rows.append(dict(round=target+1, client=0, seconds=perf_counter()-start,
                                        peer_orders=self.clients-1, edges=len(union)))
            require(all(np.array_equal(rebuilt, actual) for rebuilt, actual in zip(leader_orders, orders, strict=True)),
                    f'Round {target+1}: reconstructed requests differ from student orders')

        mask = np.zeros(self.length, dtype=np.uint8)
        mask[union] = 1
        teacher_edges = [union]
        for peer in range(1, self.clients):
            decoded = self.control(mask, 1, b'U', 0, peer, target, self.length, 'union_down_bytes')
            teacher_edges.append(np.flatnonzero(decoded))
        if self.audit_rows is not None:
            require(all(np.array_equal(edges, union) for edges in teacher_edges),
                    f'Round {target+1}: received union differs from leader')
        return union, leader_orders, teacher_edges
