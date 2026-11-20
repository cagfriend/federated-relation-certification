"""Timed windows and independent full-relation checks."""

from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import torch

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.timing import Ledger, difference, observe
from experiments.private_corrected_guard import engine as original_private
from experiments.private_corrected_guard.run import digest
from experiments.public_scaling.certification import hard_relations
from experiments.snapshot_external_comparison.run import assessment
from .design import case_id, checkpoints, legacy_eval, legacy_round, require, sha
from .engine import Engine
from .inputs import load_verified


def timed(ledger, operation):
    before = ledger.snapshot()
    with ledger.phase('compute_seconds'):
        start = perf_counter()
        value = operation()
        elapsed = perf_counter()-start
    return value, elapsed, difference(ledger.snapshot(), before)


class PrivateOrderRecorder:
    """Read the actual permutation in an audit; never touch the global NumPy RNG."""

    def __init__(self):
        self.orders = []
        self.random = SimpleNamespace(SeedSequence=np.random.SeedSequence, default_rng=self.make_rng)

    def __getattr__(self, name):
        return getattr(np, name)

    def make_rng(self, seed):
        generator = np.random.default_rng(seed)

        def permutation(n):
            result = generator.permutation(n)
            self.orders.append(result)
            return result

        return SimpleNamespace(permutation=permutation)


def expected_private(seed, rnd, private):
    return [np.random.default_rng(np.random.SeedSequence([seed, 401, c, rnd, 0])).permutation(len(x))
            for c, x in enumerate(private)]


def battery():
    try:
        import psutil
        info = psutil.sensors_battery()
        return None if info is None else info.power_plugged
    except (ImportError, OSError, AttributeError):
        return None


def peak_bytes():
    import sys
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                (k, ctypes.c_size_t) for k in ('peak_wset', 'wset', 'peak_paged', 'paged',
                                              'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]

        current = ctypes.windll.kernel32.GetCurrentProcess
        current.restype = wintypes.HANDLE
        read = ctypes.windll.psapi.GetProcessMemoryInfo
        read.argtypes = (wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD)
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        return int(counters.peak_wset) if read(current(), ctypes.byref(counters), counters.cb) else None
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == 'darwin' else 1024))


def suspend_clock():
    """Cumulative suspend time, where the OS exposes both clock types."""
    import sys
    if sys.platform == 'win32':
        import ctypes
        uptime = ctypes.windll.kernel32.GetTickCount64
        uptime.restype = ctypes.c_ulonglong
        awake = ctypes.c_ulonglong()
        if ctypes.windll.kernel32.QueryUnbiasedInterruptTime(ctypes.byref(awake)):
            return uptime()/1000 - awake.value/1e7
    elif sys.platform.startswith('linux'):
        import time
        if hasattr(time, 'CLOCK_BOOTTIME'):
            return time.clock_gettime(time.CLOCK_BOOTTIME)-time.monotonic()
    return None


def run(out, case, cfg, old, prep, *, audit_prefix=None):
    part, method, check = case['partition'], case['method'], case['stage'] == 'audit'
    require(audit_prefix is None or (check and audit_prefix in checkpoints(cfg)[1:]),
            'Development prefix must end at an audit checkpoint')
    rounds = cfg['rounds'] if audit_prefix is None else audit_prefix
    models, train, evaluation = load_verified(Path(prep['source_cache']), part, cfg, old)
    weights = out/'preparation'/f'{case_id(case)}.pt'
    require(sha(weights) == prep['selected_sha256'], 'Selected weights changed in worker')
    for model, state in zip(models, torch.load(weights, weights_only=True), strict=True):
        model.load_state_dict(state)
    require(model_digest(models) == prep['selected_model_digest'], 'Worker selected model mismatch')
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    wire, ledger = Wire(), Ledger()
    # Library warm-up uses scratch data and never touches model, graph or certificate cache.
    m = np.ones((32, 32))
    _ = m @ m
    _ = torch.ones((32, 32)) @ torch.ones((32, 32))
    input_peak = peak_bytes()
    ac_start = battery()
    suspend_start = suspend_clock()
    with observe(ledger, wire):
        a, setup_s, setup_parts = timed(ledger, lambda: Engine(
            models, cfg, wire, train['private'], train['public'], method=method, initialization='centers',
            strength=.5, until=cfg['rounds'], all_clients=True))
    a.protocol.observer = ledger
    initial = dict(model_digest=model_digest(models), head_digest=a.state_digest(), graph_digest=digest(a.edges),
                   centers=[digest(c) for c in a.centers], pseudo=[digest(y) for y in a.pseudo],
                   setup_traffic=a.traffic())
    chosen = [r['candidates'][str(r['selected'])] for r in prep['selection']]
    require(initial['centers'] == old['initial_head_sources'] == [r['centers_digest'] for r in chosen]
            and initial['pseudo'] == [r['pseudo_digest'] for r in chosen], 'Initial centers/labels changed')
    with torch.no_grad():
        features = [m.encode(evaluation['test']).double().numpy() for m in models]
    report_rounds = set(checkpoints(cfg))
    rows, evals, audit_checked = [], [], 0

    def score(rnd):
        ev = dict(round=rnd, cumulative_bytes=a.traffic().get('total_bytes', 0),
                  **assessment(a, train, evaluation, cfg, features))
        legacy = old['evaluations'][len(evals)]
        require(legacy_eval(ev) == legacy_eval(legacy), f'E38 evaluation mismatch at round {rnd}')
        evals.append(ev)

    score(0)
    total = a.traffic()
    prior_teacher = None
    # Install observers once, avoiding repeated imports/patches between rounds.
    with observe(ledger, wire):
        for rnd in range(1, rounds+1):
            op = lambda: a.round(train['private'], train['public'], cfg['seed'], rnd)
            expected = expected_private(cfg['seed'], rnd, a.private) if check else None
            if check:
                recorder = PrivateOrderRecorder()
                with patch.object(original_private, 'np', recorder):
                    stat = op()
                require(len(recorder.orders) == len(a.heads) and
                        all(np.array_equal(x, y) for x, y in zip(recorder.orders, expected)),
                        f'Private batch order mismatch at {rnd}')
                elapsed, parts = None, None
            else:
                stat, elapsed, parts = timed(ledger, op)
            relations = a.last_relations
            counts = a.protocol.counts
            if check:
                for z, (w, b), rel in zip(a.public, a.last_snapshot, relations):
                    full = hard_relations((z @ w.T + b).argmax(1), a.edges)
                    require(np.array_equal(full, rel), f'Hard relation oracle mismatch at {rnd}')
                    audit_checked += len(full)
                require(np.array_equal(np.sum(relations, axis=0), counts), f'Committed counts differ at {rnd}')
                require(all(np.array_equal(t, counts.astype(np.float64)/len(a.heads))
                            for t in stat['consumed']), f'Consumed target differs at {rnd}')
            now = a.traffic()
            snap = a.last_snapshot
            motion = None if prior_teacher is None else [
                float(np.sqrt(np.sum((w-u)**2) + np.sum((b-v)**2)))
                for (w, b), (u, v) in zip(snap, prior_teacher)]
            prior_teacher = snap
            row = dict(round=rnd, head_digest=a.state_digest(),
                       head_by_client=[(digest(h.w), digest(h.b)) for h in a.heads],
                       teachers_by_client=[(digest(w), digest(b)) for w, b in snap],
                       relation_digests=[digest(x) for x in relations], aggregate_digest=digest(counts),
                       consumed_target_digests=[digest(t[ids]) for t, ids in zip(stat['consumed'], stat['public_orders'])],
                       public_orders=[digest(x) for x in stat['public_orders']],
                       public_steps_by_client=[len(x)//a.config.public_edge_batch for x in stat['public_orders']],
                       private_losses=stat['private_losses'], public_losses=stat['public_losses'],
                       teacher_positive_rates=[float(x.mean()) for x in relations],
                       aggregate_positive_rate=float(counts.mean()/len(a.heads)),
                       traffic_delta=difference(now, total), endpoint_counts=stat['endpoints'],
                       certified_edges=stat['certified'], teacher_motion=motion)
            if check:
                row['audited_private_orders'] = [digest(x) for x in recorder.orders]
            else:
                row.update(seconds=elapsed, timing_parts=parts,
                           **{k: stat[k] for k in ('private_seconds', 'generation_seconds',
                                                  'exchange_seconds', 'public_seconds')})
            total = now
            require(legacy_round(row) == legacy_round(old['rows'][rnd-1]), f'E38 round {rnd} mismatch ({method})')
            require(all(x == min(cfg['public_steps'], len(a.edges)//a.config.public_edge_batch)
                        for x in row['public_steps_by_client']), 'Wrong public update budget')
            rows.append(row)
            if rnd in report_rounds:
                score(rnd)
    require(model_digest(models) == initial['model_digest'], 'Frozen encoder changed')
    if audit_prefix is None:
        require(total == old['traffic'], 'Final traffic changed')
    suspend_end = suspend_clock()
    return dict(case=case, cfg=cfg, initial=initial, rows=rows, evaluations=evals, traffic=total,
                audit_edges=audit_checked, cache_bytes=a.cache_bytes(), input_peak_bytes=input_peak,
                process_peak_bytes=peak_bytes(), power_plugged_start=ac_start, power_plugged_end=battery(),
                sleep_seconds_estimate=None if None in (suspend_start, suspend_end)
                else max(0., suspend_end-suspend_start),
                setup_seconds=None if check else setup_s, setup_timing=None if check else setup_parts)
