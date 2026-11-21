"""Compare both D variants on every edge and retain first divergence evidence."""

import numpy as np

from experiments.public_scaling.certification import hard_relations
from ..numerical_check.audit import ObservedGenerator, oracle, rational_rows
from .candidate import EndpointBiasGenerator


class ObservedEndpointBiasGenerator(ObservedGenerator, EndpointBiasGenerator):
    """Use the original audit probe with the experimental bias implementation."""


FACTORIES = {
    "old": lambda x, w, b, edges: ObservedGenerator(x, w, b, edges, "relation"),
    "new": ObservedEndpointBiasGenerator,
}
DIAGNOSTICS = ("edges_vs_b", "b_winner_excluded", "exact_winner_excluded", "refresh_vs_b")
CHANGES = ("fixed", "remaining", "introduced")


def observe(generator, x, weights, bias, labels_b, labels_exact, initial):
    if initial:
        return generator.initial_relations, len(x), {}, None
    relations, stats = generator.generate(weights, bias)
    state = generator.candidate_state
    ids = generator.refreshed
    indices = np.arange(len(x))
    diagnostics = {
        "b_winner_excluded": np.flatnonzero(~state["mask"][indices, labels_b]),
        "exact_winner_excluded": np.flatnonzero(~state["mask"][indices, labels_exact]),
        "refresh_vs_b": ids[generator.winners[ids] != labels_b[ids]],
    }
    details = {
        "candidate": state,
        "refreshed_ids": ids,
        "cached_winners_after": generator.winners.copy(),
    }
    return relations, stats["forward_endpoints"], diagnostics, details


def audit(case):
    x, edges = case.features, case.edges
    exact_inputs = rational_rows(x)
    generators, stopped = {}, set()
    rows, first_events, witnesses = [], {}, {}
    for index, (weights, bias) in enumerate(zip(case.weights, case.biases, strict=True)):
        scores = x @ weights.T + bias
        if not np.isfinite(scores).all():
            raise ValueError(f"Non-finite B scores in {case.name}, snapshot {index + 1}")
        labels_b = scores.argmax(axis=1)
        rel_b = hard_relations(labels_b, edges)
        exact_scores, labels_exact = oracle(exact_inputs, weights, bias)
        rel_exact = hard_relations(labels_exact, edges)
        exact_label_diff = np.flatnonzero(labels_b != labels_exact)
        exact_edge_diff = np.flatnonzero(rel_b != rel_exact)
        events = {"b_vs_exact_labels": exact_label_diff, "b_vs_exact_edges": exact_edge_diff}
        row = {"round": index + 1, "b_vs_exact_labels": len(exact_label_diff),
               "b_vs_exact_edges": len(exact_edge_diff)}
        wrong, details, exceptions = {}, {}, {}
        for name, factory in FACTORIES.items():
            for field in (*DIAGNOSTICS, "forward_endpoints"):
                row[f"{name}_{field}"] = None
            row[f"{name}_exception"] = False
            if name in stopped:
                continue
            try:
                if index == 0:
                    generators[name] = factory(x, weights, bias, edges)
                rel, forward, diagnostic, state = observe(
                    generators[name], x, weights, bias, labels_b, labels_exact, index == 0
                )
            except (ArithmeticError, ValueError) as error:
                stopped.add(name)
                exceptions[name] = {"type": type(error).__name__, "message": str(error)}
                row[f"{name}_exception"] = True
                continue
            wrong[name] = rel != rel_b
            details[name] = {"relations": rel, "state": state}
            row[f"{name}_forward_endpoints"] = forward
            for key in DIAGNOSTICS:
                indices = (np.flatnonzero(wrong[name]) if key == "edges_vs_b"
                           else diagnostic.get(key, ()))
                events[f"{name}_{key}"] = indices
                row[f"{name}_{key}"] = len(indices)

        changes = {}
        if len(wrong) == len(FACTORIES):
            changes = {
                "fixed": wrong["old"] & ~wrong["new"],
                "remaining": wrong["old"] & wrong["new"],
                "introduced": ~wrong["old"] & wrong["new"],
            }
        for key in CHANGES:
            indices = np.flatnonzero(changes[key]) if key in changes else None
            row[key] = None if indices is None else len(indices)
            if indices is not None:
                events[key] = indices
        first = {key: list(map(int, values)) for key, values in events.items()
                 if len(values) and key not in first_events}
        first.update({f"{key}_exception": error for key, error in exceptions.items()})
        if first:
            for key, value in first.items():
                first_events[key] = {"round": row["round"], "detail": value}
            witnesses[str(row["round"])] = {
                "b_labels": labels_b.tolist(),
                "exact_labels": labels_exact.tolist(),
                "b_relations": rel_b.tolist(),
                "exact_relations": rel_exact.tolist(),
                "b_scores": scores.tolist(),
                "exact_scores": [[str(score) for score in values] for values in exact_scores],
                "methods": {
                    key: {"relations": value["relations"].tolist(), "state": serialize_state(value["state"])}
                    for key, value in details.items()
                },
            }
        rows.append(row)
    return rows, first_events, witnesses


def serialize_state(state):
    if state is None:
        return None
    return {
        "candidate": {key: value.tolist() for key, value in state["candidate"].items()},
        "refreshed_ids": state["refreshed_ids"].tolist(),
        "cached_winners_after": state["cached_winners_after"].tolist(),
    }
