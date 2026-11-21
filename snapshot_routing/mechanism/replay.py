"""Separate relation-only certificates from savings across evolving caches."""

import numpy as np

from experiments.public_scaling.certification import RelationGenerator
from experiments.snapshot_certification_timing.design import require

STATE_FIELDS = ('both_singletons', 'same_singleton_edges', 'disjoint_edges', 'extra_edges',
                'unresolved_edges', 'point_forward', 'relation_forward')


def from_candidates(bits, singleton, edges):
    left, right = edges.T
    both = singleton[left] & singleton[right]
    disjoint = (bits[left] & bits[right]) == 0
    same = both & (bits[left] == bits[right])
    unresolved = ~(disjoint | same)
    needed = np.zeros(len(bits), dtype=bool)
    needed[edges[unresolved].ravel()] = True
    return dict(both_singletons=int(both.sum()), same_singleton_edges=int(same.sum()),
                disjoint_edges=int(disjoint.sum()), extra_edges=int((disjoint & ~both).sum()),
                unresolved_edges=int(unresolved.sum()), point_forward=int((~singleton).sum()),
                relation_forward=int((needed & ~singleton).sum()))


class PointObserver(RelationGenerator):
    def candidate_matrix(self):
        candidates = super().candidate_matrix()
        bits = (candidates.astype(np.uint64)*self.powers).sum(axis=1, dtype=np.uint64)
        singleton = (bits & (bits - np.uint64(1))) == 0
        self.observation = from_candidates(bits, singleton, self.edges)
        return candidates


class RelationObserver(RelationGenerator):
    def candidate_sets(self):
        candidates, bits, singleton = super().candidate_sets()
        self.observation = from_candidates(bits, singleton, self.edges)
        return candidates, bits, singleton


def replay(trace, cfg, *, prefix=None):
    rounds = cfg['rounds'] if prefix is None else prefix
    clients = len(cfg['widths'])
    samples = cfg['public_size']
    edges = trace['edges']
    packed = trace['relations']
    require(1 <= rounds <= cfg['rounds'] and edges.shape == (samples//2, 2) and
            np.array_equal(np.sort(edges.ravel()), np.arange(samples)) and
            packed.shape == (cfg['rounds'], clients, (len(edges)+7)//8), 'Unexpected matching graph or trace dimensions')
    rows = [dict(round=r+1, clients=[]) for r in range(rounds)]
    memory = {'E': 0, 'D': 0}
    # Replay one client at a time. Every method retains that client's independent cache.
    for client, width in enumerate(cfg['widths']):
        x, w, b = (trace[f'{prefix}{client}'] for prefix in ('x','w','b'))
        k = cfg['classes']
        require(x.shape == (samples, width) and w.shape == (cfg['rounds'], k, width)
                and b.shape == (cfg['rounds'], k), f'Unexpected client {client} features or head shape')
        point = PointObserver(x, w[0], b[0], edges, 'point')
        relation = RelationObserver(x, w[0], b[0], edges, 'relation')
        first_e, first_d = point.initial_relations, relation.initial_relations
        del point.initial_relations, relation.initial_relations
        for m, g in (('E', point), ('D', relation)):
            memory[m] += sum(g.persistent_arrays().values())
        for r in range(rounds):
            expected = np.unpackbits(packed[r, client], count=len(edges))
            if r == 0:
                e, d = first_e, first_d
                item = dict(e_forward=samples, d_forward=samples, e_state=None, d_state=None)
            else:
                e, e_stats = point.generate(w[r], b[r])
                d, d_stats = relation.generate(w[r], b[r])
                es, ds = point.observation, relation.observation
                require(es['point_forward'] == e_stats['forward_endpoints'] and
                        ds['relation_forward'] == d_stats['forward_endpoints'] and
                        ds['unresolved_edges'] == d_stats['unresolved_edges_before_refresh'] and
                        es['both_singletons'] == e_stats['certified_edges_before_refresh'],
                        f'Inconsistent certificate instrumentation at client {client}, round {r+1}')
                item = dict(e_forward=e_stats['forward_endpoints'], d_forward=d_stats['forward_endpoints'],
                            e_state=es, d_state=ds)
            require(np.array_equal(e, expected) and np.array_equal(d, expected),
                    f'Relation mismatch against B at client {client}, round {r+1}')
            rows[r]['clients'].append(dict(client=client, width=width, **item))
    return dict(rows=rows, cache_bytes=memory, comparisons=rounds*clients*len(edges)*2)
