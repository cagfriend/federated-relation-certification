"""Reuse the E38 learning engine with a larger nested public bank."""

from collections import Counter

import numpy as np
import torch

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.timing import Ledger, difference, observe
from experiments.private_corrected_guard.run import digest
from experiments.public_scaling.certification import hard_relations, make_matching
from experiments.snapshot_certification_timing.design import checkpoints, legacy_eval, legacy_round, require
from experiments.snapshot_certification_timing.engine import Engine
from experiments.snapshot_certification_timing.worker import battery, peak_bytes, suspend_clock, timed
from experiments.snapshot_external_comparison.run import assessment
from .inputs import load_bank, selected_models


def run(out, case, base, cfg, prep_dir, cache, old, anchors, bank, *, prefix=None):
    audit = case['stage'] == 'audit'
    native = cfg['public_size'] == base['public_size']
    rounds = cfg['rounds'] if prefix is None else prefix
    require(prefix is None or (audit and prefix in checkpoints(cfg)[1:]), 'Invalid development prefix')
    models, train, evaluation, prep = selected_models(prep_dir, case, base, cache, old, anchors)
    public, ids = load_bank(out, case, train, bank)
    id_hash = digest(ids.numpy())
    # Materialize first so disk I/O from mmap is never charged to model setup.
    public = public.clone()
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    warm = np.ones((32, 32))
    _ = warm @ warm
    _ = torch.ones((32, 32)) @ torch.ones((32, 32))
    base_peak = peak_bytes()
    power = Counter()

    def power_check():
        state = battery()
        power['unknown' if state is None else ('ac' if state else 'battery')] += 1

    if not audit:
        power_check()
    begin_sleep = suspend_clock()
    wire, ledger = Wire(), Ledger()
    with observe(ledger, wire):
        a, setup, setup_parts = timed(ledger, lambda: Engine(
            models, cfg, wire, train['private'], public, method=case['method'], initialization='centers',
            strength=.5, until=cfg['rounds'], all_clients=True))
    a.protocol.observer = ledger
    initial = dict(model_digest=model_digest(models), head_digest=a.state_digest(),
                   graph_digest=digest(a.edges), public_ids_digest=id_hash,
                   centers=[digest(x) for x in a.centers], pseudo=[digest(y) for y in a.pseudo],
                   setup_traffic=a.traffic())
    chosen = [r['candidates'][str(r['selected'])] for r in prep['selection']]
    require(initial['model_digest'] == old['selected_model_digest'] and
            initial['centers'] == old['initial_head_sources'] == [r['centers_digest'] for r in chosen] and
            initial['pseudo'] == [r['pseudo_digest'] for r in chosen], 'Initial model/centers/pseudo labels changed')
    require(np.array_equal(a.edges, make_matching(len(public), cfg['seed'])) and
            np.array_equal(np.sort(a.edges.ravel()), np.arange(len(public))), 'Graph is not the fixed matching')
    with torch.no_grad():
        features = [m.encode(evaluation['test']).double().numpy() for m in models]
    rows, evals, checked = [], [], 0
    ticks = set(checkpoints(cfg))

    def qualify(rnd):
        ev = dict(round=rnd, cumulative_bytes=a.traffic().get('total_bytes', 0),
                  **assessment(a, train, evaluation, cfg, features))
        if native:
            require(legacy_eval(ev) == legacy_eval(old['evaluations'][len(evals)]),
                    f'E38 baseline evaluation mismatch at {rnd}')
        evals.append(ev)

    qualify(0)
    previous = a.traffic()
    prior_teacher = None
    batch = a.config.public_edge_batch
    expected_edges = min(len(a.edges), cfg['public_steps'] * batch)
    with observe(ledger, wire):
        for rnd in range(1, rounds+1):
            def step():
                return a.round(train['private'], public, cfg['seed'], rnd)
            if audit:
                stat = step()
                elapsed, parts = None, None
            else:
                stat, elapsed, parts = timed(ledger, step)
            rel, committed = a.last_relations, a.protocol.counts
            snapshot = a.last_snapshot
            if audit:
                for c, (z, (w, b), vec) in enumerate(zip(a.public, snapshot, rel)):
                    exact = hard_relations((z @ w.T + b).argmax(axis=1), a.edges)
                    require(np.array_equal(exact, vec), f'Wrong relation at round {rnd}, client {c}')
                    require(np.array_equal(committed.astype(np.float64)/len(a.heads), stat['consumed'][c]),
                            f'Wrong consumed targets at round {rnd}, client {c}')
                    checked += len(exact)
                require(np.array_equal(committed, np.sum(rel, axis=0)), f'Wrong aggregate at round {rnd}')
            orders = stat['public_orders']
            require(all(len(order) == expected_edges for order in orders), 'Student budget changed')
            if audit:
                for c, order in enumerate(orders):
                    expected = np.random.default_rng(np.random.SeedSequence(
                        [cfg['seed'], 402, c, rnd, 0])).permutation(len(a.edges))[:expected_edges]
                    require(np.array_equal(order, expected), 'Student edge order changed')
            now = a.traffic()
            motion = None if prior_teacher is None else [float(np.sqrt(np.sum((w-u)**2)+np.sum((b-v)**2)))
                for (w, b), (u, v) in zip(snapshot, prior_teacher)]
            row = dict(round=rnd, head_digest=a.state_digest(),
                       teacher_by_client=[(digest(w), digest(b)) for w, b in snapshot],
                       relations=[digest(x) for x in rel], aggregate=digest(committed),
                       targets_used=[digest(t[o]) for t, o in zip(stat['consumed'], orders)],
                       student_orders=[digest(o) for o in orders], student_edges=[len(o) for o in orders],
                       teacher_positive_rates=[float(x.mean()) for x in rel],
                       aggregate_positive_rate=float(committed.mean()/len(a.heads)),
                       private_losses=stat['private_losses'], public_losses=stat['public_losses'],
                       traffic_delta=difference(now, previous), endpoint_counts=stat['endpoints'],
                       certified_edges=stat['certified'], teacher_motion=motion)
            if native:
                require(legacy_round(row) == legacy_round(old['rows'][rnd-1]), f'E38 baseline mismatch at {rnd}')
            if not audit:
                row.update(seconds=elapsed, timing_parts=parts,
                           **{k: stat[k] for k in ('private_seconds','generation_seconds','exchange_seconds','public_seconds')})
            rows.append(row)
            previous = now
            prior_teacher = snapshot
            if rnd in ticks:
                qualify(rnd)
                if not audit:
                    power_check()
    require(model_digest(models) == initial['model_digest'], 'Frozen encoder changed')
    if native and prefix is None:
        require(previous == old['traffic'], 'E38 final traffic mismatch')
    end_sleep = suspend_clock()
    return dict(case=case, cfg=cfg, initial=initial, rows=rows, evaluations=evals, traffic=previous,
                audit_edges=checked, cache_bytes=a.cache_bytes(), input_peak_bytes=base_peak,
                process_peak_bytes=peak_bytes(), protocol_bytes=a.protocol.persistent_bytes(),
                power=dict(power), sleep_seconds_estimate=None if None in (begin_sleep, end_sleep)
                else max(0., end_sleep-begin_sleep), setup_seconds=None if audit else setup,
                setup_timing=None if audit else setup_parts)
