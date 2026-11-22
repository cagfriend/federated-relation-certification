"""Localize wrong edges against B, then replay independent safeguards."""

from functools import partial
from fractions import Fraction

import numpy as np

from experiments.public_scaling.certification import RelationGenerator, hard_relations
from experiments.snapshot_certification_timing.design import require
from ..bias_numerical.audit import ObservedEndpointBiasGenerator
from ..numerical_check.audit import oracle, rational_rows
from .guard import GuardedGenerator

REPAIRS = ('weight', 'dense', 'combined')
METHODS = ('current', *REPAIRS)


class PrefixProbe:
    """Exact sum of the computed float increments for the weight-only fixtures."""

    def __init__(self, initial):
        self.previous = initial
        shape = (len(initial),) * 2
        self.history = [np.full(shape, Fraction(0), dtype=object)]

    def masks(self, state, weights):
        delta = weights - self.previous
        increments = np.linalg.norm(delta[:, None, :] - delta[None, :, :], axis=2)
        exact = self.history[-1] + np.vectorize(Fraction.from_float, otypes=[object])(increments)
        self.history.append(exact)
        self.previous = weights
        winners = state['winners']
        before = np.stack([self.history[rnd][winner] for rnd, winner in zip(
            state['reference_round'], winners, strict=True)])
        movement = (exact[winners] - before).astype(np.float64)
        bound = state['radius'][:, None] * movement + state['bias_now'] - state['bias_then']
        bound += 1e-10 * (1 + np.abs(bound) + np.abs(state['gaps']))
        return state['gaps'] <= bound


def relations_from_mask(x, w, b, edges, mask, b_labels=None):
    size = mask.sum(1)
    require(np.all(size > 0), 'Empty candidate set in diagnostic')
    left, right = edges.T
    singleton = size == 1
    disjoint = ~(mask[left] & mask[right]).any(1)
    unresolved = ~(disjoint | (singleton[left] & singleton[right]))
    needed = np.zeros(len(x), dtype=bool)
    needed[edges[unresolved].ravel()] = True
    ids = np.flatnonzero(needed & ~singleton)
    labels = mask.argmax(1)
    if b_labels is None:
        labels[ids] = (x[ids] @ w.T + b).argmax(1)
    else:
        labels[ids] = b_labels[ids]
    final = mask.copy()
    final[ids] = False
    final[ids, labels[ids]] = True
    known = final.sum(1) == 1
    disjoint = ~(final[left] & final[right]).any(1)
    same = known[left] & known[right] & (labels[left] == labels[right])
    return np.where(disjoint | same, same, -1)


def audit(case):
    x, edges = case.features, case.edges
    w0, b0 = case.weights[0], case.biases[0]
    factories = dict(current=ObservedEndpointBiasGenerator,
                     weight=partial(GuardedGenerator, interval=True, dense=False),
                     dense=partial(GuardedGenerator, interval=False, dense=True),
                     combined=partial(GuardedGenerator, interval=True, dense=True))
    models = {name: make(x, w0, b0, edges) for name, make in factories.items()}
    old = RelationGenerator(x, w0, b0, edges, 'relation')
    prefix = PrefixProbe(w0) if case.family == 'heldout_weight_prefix' else None
    rationals = rational_rows(x)
    rounds, events = [], []
    for rnd, (w, b) in enumerate(zip(case.weights, case.biases, strict=True), 1):
        b_labels = (x @ w.T + b).argmax(1)
        b_edges = hard_relations(b_labels, edges)
        _, rational_labels = oracle(rationals, w, b)
        rational_edges = hard_relations(rational_labels, edges)
        old_rel = old.initial_relations if rnd == 1 else old.generate(w, b)[0]
        values, points = {}, {}
        for name, model in models.items():
            if rnd == 1:
                values[name], points[name] = model.initial_relations, len(x)
            else:
                values[name], stats = model.generate(w, b)
                points[name] = stats['forward_endpoints']
        wrong = {name: value != b_edges for name, value in values.items()}
        original = wrong['current']
        old_wrong = old_rel != b_edges
        row = dict(case=case.name, round=rnd, edges=len(edges), b_vs_rational=int((b_edges != rational_edges).sum()),
                   old_wrong=int(old_wrong.sum()), current_wrong=int(original.sum()),
                   current_introduced_vs_old=int((original & ~old_wrong).sum()), current_forward=points['current'])
        for name in REPAIRS:
            row.update({f'{name}_wrong': int(wrong[name].sum()),
                        f'{name}_fixed': int((original & ~wrong[name]).sum()),
                        f'{name}_remaining': int((original & wrong[name]).sum()),
                        f'{name}_introduced': int((~original & wrong[name]).sum()),
                        f'{name}_forward': points[name], f'{name}_fallback': models[name].fallback})
        rounds.append(row)
        intervention = {}
        if rnd > 1:
            current = models['current']
            state = current.candidate_state
            mask = state['mask']
            weights_mask = prefix.masks(state, w) if prefix else None
            excluded = ~mask[np.arange(len(x)), b_labels]
            refresh = np.zeros(len(x), dtype=bool)
            ids = current.refreshed
            refresh[ids] = current.winners[ids] != b_labels[ids]
            if original.any():
                reproduced = relations_from_mask(x, w, b, edges, mask)
                require(np.array_equal(reproduced, values['current']), f'{case.name} round {rnd}: probe changed D')
                augmented = mask.copy()
                augmented[np.arange(len(x)), b_labels] = True
                intervention = dict(
                    b_winner_excluded=excluded[edges].any(1),
                    local_refresh_disagrees=refresh[edges].any(1),
                    rescue_candidate_matches=relations_from_mask(x, w, b, edges, augmented) == b_edges,
                    b_slice_refresh_matches=relations_from_mask(x, w, b, edges, mask, b_labels) == b_edges,
                    both_probes_match=relations_from_mask(x, w, b, edges, augmented, b_labels) == b_edges,
                )
                require(intervention['both_probes_match'].all(), f'{case.name} round {rnd}: oracle probes disagree')
                if weights_mask is not None:
                    intervention['exact_prefix_matches'] = relations_from_mask(x, w, b, edges, weights_mask) == b_edges
        for i in np.flatnonzero(np.logical_or.reduce(tuple(wrong.values()))):
            left, right = edges[i]
            event = dict(case=case.name, round=rnd, edge=int(i), left=int(left), right=int(right),
                         b=int(b_edges[i]), rational=int(rational_edges[i]), old_d=int(old_rel[i]),
                         **{name: int(values[name][i]) for name in METHODS})
            for field in ('b_winner_excluded', 'local_refresh_disagrees', 'rescue_candidate_matches',
                          'b_slice_refresh_matches', 'both_probes_match', 'exact_prefix_matches'):
                event[field] = bool(intervention[field][i]) if original[i] and field in intervention else None
            events.append(event)
    return rounds, events
