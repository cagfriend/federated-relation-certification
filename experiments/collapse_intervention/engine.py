"""Controlled, observational collapse interventions over workload method B."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import time

import numpy as np

from experiments.private_workload import engine as original
from experiments.stl10_diagnostics.probes import fixed_public_indices, probe
from experiments.public_scaling.engine import evaluate, heads_digest


ARMS = ("private_only", "public1", "public2_half", "reference2")


@contextmanager
def _patched(private, public):
    old_private, old_public = original.private_workload_epoch, original.update
    original.private_workload_epoch, original.update = private, public
    try:
        yield old_private, old_public
    finally:
        original.private_workload_epoch, original.update = old_private, old_public


def _derived_spec(base_spec, arm):
    if arm == "public1":
        return replace(base_spec, steps=1)
    if arm == "public2_half":
        return replace(base_spec, config=replace(
            base_spec.config, public_weight=base_spec.config.public_weight * 0.5))
    return base_spec


def drive(data, base_spec, arm, *, observations=True, progress=False) -> dict:
    """Run one arm, wrapping the original private and public update callbacks.

    Diagnostic time is recorded separately. Engine phase timings also include
    probes inside the callback hooks.
    """
    if arm not in ARMS:
        raise ValueError(f"Unknown intervention arm: {arm}")
    spec = _derived_spec(base_spec, arm)
    spec.validate()
    cfg = spec.config
    model = original.WorkloadMethod("B", data, spec)
    initial = heads_digest(model.heads)
    records, stages, metrics = [], [], []
    diagnostic_seconds = 0.0
    evaluation_seconds = 0.0
    checkpoints = {0, 1, 2, 5, 10, cfg.rounds, *range(20, cfg.rounds + 1, 20)}

    def client_state(client):
        h = model.heads[client]
        return {
            "client": client,
            "private": probe(h, data.private[client], data.pseudo[client]),
            "public": probe(h, data.public[client], indices=fixed_public_indices(cfg, data.seed, client)),
        }

    def capture_all(rnd, phase):
        nonlocal diagnostic_seconds
        start = time.perf_counter()
        items = [client_state(c) for c in range(len(model.heads))]
        diagnostic_seconds += time.perf_counter() - start
        stages.append({"round": rnd, "phase": phase, "clients": items})

    def evaluate_now(rnd):
        nonlocal evaluation_seconds
        start = time.perf_counter()
        result = dict(round=rnd, **evaluate(model.heads, data, cfg))
        evaluation_seconds += time.perf_counter() - start
        metrics.append(result)

    if observations:
        capture_all(0, "initial")
        evaluate_now(0)

    old_private, old_public = original.private_workload_epoch, original.update
    for rnd in range(1, cfg.rounds + 1):
        observe_round = observations and rnd in checkpoints
        private_digest = None
        public_after = []

        def private_callback(head, z, y, config, seed, client, round_number, limit):
            nonlocal diagnostic_seconds
            result = old_private(head, z, y, config, seed, client, round_number, limit)
            if observe_round:
                start = time.perf_counter()
                item = client_state(client)
                diagnostic_seconds += time.perf_counter() - start
                stages_private.append(item)
            return result

        stages_private = []

        def public_callback(head, z, edges, targets, update_spec, seed, client, round_number):
            nonlocal private_digest, diagnostic_seconds
            if private_digest is None:
                private_digest = heads_digest(model.heads)
                if observe_round:
                    stages.append({"round": rnd, "phase": "after_private", "clients": stages_private})
            if arm == "private_only":
                result = (0.0, 0, np.empty(0, dtype=np.int64))
            else:
                result = old_public(head, z, edges, targets, update_spec, seed, client, round_number)
            if observe_round:
                start = time.perf_counter()
                public_after.append(client_state(client))
                diagnostic_seconds += time.perf_counter() - start
            return result

        with _patched(private_callback, public_callback):
            row, _, _, orders = model.step(rnd)

        if private_digest is None:
            raise RuntimeError('Missing public callback boundary')
        row["head_digest_after_private"] = private_digest
        row["public_order_digests"] = [hashlib.sha256(np.asarray(order, dtype="<u4").tobytes()).hexdigest()
                                        for order in orders]
        row["public_targets_applied"] = arm != "private_only"
        if arm == "private_only":
            row["public_optimizer_steps"] = 0
            row["public_loss"] = None
        records.append(row)

        if observe_round:
            stages.append({"round": rnd, "phase": "after_public", "clients": public_after})
            if rnd in checkpoints:
                evaluate_now(rnd)
        if progress:
            print(f"{arm}: {rnd}/{cfg.rounds}", flush=True)

    return {
        "arm": arm,
        "spec": spec.json(),
        "rounds": cfg.rounds,
        "initial_head_digest": initial,
        "final_head_digest": heads_digest(model.heads),
        "graph_sha256": hashlib.sha256(data.edges.astype("<u4").tobytes()).hexdigest(),
        "round_records": records,
        "metrics": metrics,
        "stages": stages,
        "diagnostic_seconds": diagnostic_seconds,
        "evaluation_seconds": evaluation_seconds,
    }
