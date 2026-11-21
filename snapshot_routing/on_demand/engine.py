"""Demand generation with the original private and public SGD arithmetic."""

from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from experiments.external_pilot import ours
from experiments.public_budget.student import selected_edges
from experiments.public_scaling.certification import hard_relations
from experiments.public_scaling.head import relation_loss_grad
from experiments.snapshot_certification_timing.engine import Engine

from .protocol import DemandProtocol


class DemandEngine(Engine):
    def __init__(self, *args, **kwargs):
        # Isolate the inherited initializer's protocol choice to this worker.
        with patch.object(ours, 'RelationProtocol', DemandProtocol):
            super().__init__(*args, method='B', **kwargs)

    def round(self, private, public, seed, rnd):
        start = perf_counter()
        self.guard_stats = []
        private_losses = [self.private_update(head, self.private[c], self.pseudo[c], self.config, seed, c, rnd)[0]
                          for c, head in enumerate(self.heads)]
        private_seconds = perf_counter()-start

        start = perf_counter()
        spec = SimpleNamespace(config=self.config, policy='fixed', steps=self.cfg['public_steps'])
        orders = [selected_edges(spec, seed, c, rnd) for c in range(len(self.heads))]
        union, leader_orders, teacher_edges = self.protocol.needs(orders, rnd-1)
        coordination_seconds = perf_counter()-start

        start = perf_counter()
        self.last_snapshot = [(head.w.copy(), head.b.copy()) for head in self.heads]
        votes, endpoints = [], []
        for teacher_ids, features, (weights, bias) in zip(teacher_edges, self.public, self.last_snapshot, strict=True):
            points, inverse = np.unique(self.edges[teacher_ids].ravel(), return_inverse=True)
            labels = (features[points]@weights.T+bias).argmax(axis=1)
            votes.append(hard_relations(labels, inverse.reshape(-1, 2)))
            endpoints.append(len(points))
        generation_seconds = perf_counter()-start

        start = perf_counter()
        counts, per_client = self.protocol.exchange_demand(votes, union, leader_orders, rnd-1)
        exchange_seconds = perf_counter()-start

        start = perf_counter()
        losses, consumed = [], []
        batch = self.config.public_edge_batch
        for c, (head, ids, targets) in enumerate(zip(self.heads, orders, per_client, strict=True)):
            fractions = targets.astype(np.float64)/len(self.heads)
            weight = self.config.head_lr*self.cfg['public_weights'][c]
            loss_sum = 0.
            for offset in range(0, len(ids), batch):
                edges = ids[offset:offset+batch]
                vertices, inverse = np.unique(self.edges[edges].ravel(), return_inverse=True)
                loss, dw, db = relation_loss_grad(self.public[c][vertices], inverse.reshape(-1, 2),
                                                 fractions[offset:offset+len(edges)], head.w, head.b)
                head.apply(dw, db, weight)
                loss_sum += loss*len(edges)
            losses.append(loss_sum/len(ids))
            consumed.append(fractions)
        self.last_relations = [v.copy() for v in votes]
        self.last_union = union
        self.last_counts = counts
        public_seconds = perf_counter()-start
        return dict(private_losses=private_losses, public_losses=losses, public_orders=orders, consumed=consumed,
                    endpoints=endpoints, private_seconds=private_seconds, coordination_seconds=coordination_seconds,
                    generation_seconds=generation_seconds, exchange_seconds=exchange_seconds,
                    public_seconds=public_seconds)
