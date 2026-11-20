"""One training path; the relation generator is the only method switch."""

from time import perf_counter
from types import SimpleNamespace

import numpy as np

from experiments.private_corrected_guard.engine import CorrectedGuardOurs
from experiments.public_budget.student import update
from experiments.public_scaling.certification import RelationGenerator

MODES = {'B': 'full', 'E': 'point', 'D': 'relation'}


class Engine(CorrectedGuardOurs):
    def __init__(self, *args, method, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = MODES[method]

    def round(self, private, public, seed, rnd):
        start = perf_counter()
        self.guard_stats = []
        private_losses = [self.private_update(h, self.private[c], self.pseudo[c], self.config,
                                             seed, c, rnd)[0] for c, h in enumerate(self.heads)]
        private_s = perf_counter() - start
        start = perf_counter()
        self.last_snapshot = [(h.w.copy(), h.b.copy()) for h in self.heads]
        relations, endpoints, certified = [], [], []
        for c, (w, b) in enumerate(self.last_snapshot):
            if rnd == 1:
                generator = RelationGenerator(self.public[c], w, b, self.edges, self.mode)
                self.generators.append(generator)
                relation = generator.initial_relations
                del generator.initial_relations
                points, edges = len(public), 0
            else:
                relation, stats = self.generators[c].generate(w, b)
                points, edges = stats['forward_endpoints'], stats['certified_edges_before_refresh']
            relations.append(relation)
            endpoints.append(points)
            certified.append(edges)
        generation_s = perf_counter() - start
        start = perf_counter()
        self.protocol.exchange(relations)
        exchange_s = perf_counter() - start
        start = perf_counter()
        losses, orders, consumed = [], [], []
        for c, head in enumerate(self.heads):
            conf = SimpleNamespace(**vars(self.config))
            conf.public_weight = self.cfg['public_weights'][c]
            spec = SimpleNamespace(config=conf, policy='fixed', steps=self.cfg['public_steps'])
            targets = self.protocol.client_counts[c].astype(np.float64)/len(self.heads)
            loss, _, order = update(head, self.public[c], self.edges, targets, spec, seed, c, rnd)
            losses.append(loss)
            orders.append(order)
            consumed.append(targets)
        self.last_relations = [r.copy() for r in relations]
        public_s = perf_counter() - start
        return dict(private_seconds=private_s, generation_seconds=generation_s,
                    exchange_seconds=exchange_s, public_seconds=public_s,
                    private_losses=private_losses, public_losses=losses, public_orders=orders,
                    consumed=consumed, endpoints=endpoints, certified=certified)

    def cache_bytes(self):
        return sum(v.nbytes for g in self.generators for k, v in vars(g).items()
                   if isinstance(v, np.ndarray) and k not in ('features', 'edges'))
