"""Compare deployed binary64 relation generation with an independent exact oracle."""

from fractions import Fraction

import numpy as np

from experiments.public_scaling.certification import RelationGenerator, hard_relations
from experiments.snapshot_certification_timing.design import require

MODES = {'E': 'point', 'D': 'relation'}


class ObservedGenerator(RelationGenerator):
    """Capture pre-refresh state while using the production generator."""

    candidate_state = None
    refreshed = None

    def candidate_matrix(self):
        mask = super().candidate_matrix()
        winners = self.winners
        self.candidate_state = dict(mask=mask.copy(), winners=winners.copy(),
                                    reference_round=self.last_evaluated.copy(), gaps=self.gaps.copy(),
                                    radius=self.radius.copy(),
                                    weight_now=self.weight_prefix[winners].copy(),
                                    weight_then=self.weight_at.copy(),
                                    bias_now=self.bias_prefix[winners].copy(),
                                    bias_then=self.bias_at.copy())
        return mask

    def _refresh(self, ids, weights, bias):
        super()._refresh(ids, weights, bias)
        self.refreshed = ids.copy()


def rational_rows(array):
    return [[Fraction.from_float(float(x)) for x in row] for row in array]


def oracle(features, weights, bias):
    exact_w = rational_rows(weights)
    exact_b = [Fraction.from_float(float(x)) for x in bias]
    exact_scores = [[sum(a*b for a,b in zip(row, head, strict=True) if a and b)+offset
                     for head, offset in zip(exact_w, exact_b, strict=True)] for row in features]
    exact_labels = np.asarray([max(range(len(row)), key=row.__getitem__) for row in exact_scores])
    return exact_scores, exact_labels


def audit(case):
    x, edges = case.features, case.edges
    bgen = RelationGenerator(x, case.weights[0], case.biases[0], edges, 'full')
    generators = {m: ObservedGenerator(x, case.weights[0], case.biases[0], edges, mode) for m,mode in MODES.items()}
    # Keep only the exact input features across snapshots. The oracle never
    # reads candidate sets or BLAS outputs when determining its winners.
    features = rational_rows(x)
    events, rows = {}, []
    stopped = set()
    indices = np.arange(len(x))
    for i, (weights, bias) in enumerate(zip(case.weights, case.biases, strict=True)):
        rnd = i+1
        scores = x @ weights.T + bias
        require(np.isfinite(scores).all(), f'{case.name} round {rnd}: non-finite dense logits')
        b_labels = scores.argmax(axis=1)
        b_rel = bgen.generate(weights,bias)[0] if i else bgen.initial_relations
        require(np.array_equal(b_rel, hard_relations(b_labels, edges)), 'Independent dense B relation differed')
        exact_scores, exact_labels = oracle(features, weights, bias)
        exact_rel = hard_relations(exact_labels, edges)
        b_labels_diff = np.flatnonzero(b_labels != exact_labels)
        b_edges_diff = np.flatnonzero(b_rel != exact_rel)
        row = dict(round=rnd, b_vs_exact_labels=len(b_labels_diff), b_vs_exact_edges=len(b_edges_diff))

        def witness():
            return dict(round=rnd, b_labels=b_labels.tolist(), exact_labels=exact_labels.tolist(),
                        b_relations=b_rel.tolist(), exact_relations=exact_rel.tolist(),
                        b_scores=scores.tolist(), exact_scores=[[str(x) for x in row] for row in exact_scores])

        if (len(b_labels_diff) or len(b_edges_diff)) and 'B_vs_exact' not in events:
            events['B_vs_exact'] = dict(witness(), label_indices=b_labels_diff.tolist(),
                                        edge_indices=b_edges_diff.tolist())
        for method, generator in generators.items():
            if method in stopped:
                for k in ('edges_vs_b', 'b_label_excluded', 'exact_label_excluded', 'refresh_vs_b', 'forward'):
                    row[f'{method}_{k}'] = None
                row[f'{method}_exception'] = False
                continue
            try:
                if i:
                    generator.candidate_state = generator.refreshed = None
                    vec, stat = generator.generate(weights, bias)
                    forward = stat['forward_endpoints']
                else:
                    vec, forward = generator.initial_relations, len(x)
            except (ArithmeticError, ValueError) as exc:
                events[f'{method}_exception'] = dict(witness(), exception=type(exc).__name__, message=str(exc))
                stopped.add(method)
                row.update({f'{method}_{k}':None for k in
                            ('edges_vs_b','b_label_excluded','exact_label_excluded','refresh_vs_b','forward')})
                row[f'{method}_exception'] = True
                continue
            state = generator.candidate_state
            ref_ids = generator.refreshed
            b_excluded = np.flatnonzero(~state['mask'][indices,b_labels]) if state is not None else np.empty(0,dtype=int)
            exact_excluded = (np.flatnonzero(~state['mask'][indices,exact_labels]) if state is not None
                              else np.empty(0,dtype=int))
            refresh_diff = (ref_ids[generator.winners[ref_ids] != b_labels[ref_ids]] if ref_ids is not None
                            else np.empty(0,dtype=int))
            edges_diff = np.flatnonzero(vec != b_rel)
            row.update({f'{method}_{k}':len(value) for k,value in
                        [('edges_vs_b',edges_diff),('b_label_excluded',b_excluded),
                         ('exact_label_excluded',exact_excluded),('refresh_vs_b',refresh_diff)]})
            row.update({f'{method}_exception':False, f'{method}_forward':forward})

            first = [k for k,v in [('edges_vs_b',edges_diff),('b_label_excluded',b_excluded),
                                  ('exact_label_excluded',exact_excluded),('refresh_vs_b',refresh_diff)]
                     if len(v) and f'{method}_{k}' not in events]
            if first:
                affected = set(edges[edges_diff].ravel().tolist())
                detail = dict(witness(), generated_relations=vec.tolist(), edge_indices=edges_diff.tolist(),
                              b_labels_excluded=b_excluded.tolist(), exact_labels_excluded=exact_excluded.tolist(),
                              refresh_vs_b_indices=refresh_diff.tolist(),
                              refreshed_indices=ref_ids.tolist() if ref_ids is not None else [],
                              cached_labels_after=generator.winners.tolist(),
                              candidate_state={k:v.tolist() for k,v in state.items()} if state is not None else None,
                              evidence_different_edges=dict(
                                  excluded_endpoints=sorted(affected.intersection(b_excluded.tolist())),
                                  refresh_disagreement_endpoints=sorted(affected.intersection(refresh_diff.tolist()))))
                for key in first:
                    events[f'{method}_{key}'] = detail
        rows.append(row)
    return rows, events
