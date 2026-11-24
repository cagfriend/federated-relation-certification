"""Screen feature collection on the original Fashion-MNIST D refresh schedule."""

from collections import defaultdict
from itertools import permutations
from statistics import mean
from time import perf_counter
from unittest.mock import patch

import numpy as np

from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_certification_timing.worker import battery, suspend_clock
from ..fashion_confirmation import worker as fashion
from ..report import eligible
from .gather import ALLOCATE, BASE, METHODS, REUSE, Collector, generator_factory

SCREEN_THRESHOLD = 10.
MIN_SCREEN_SEEDS = 2
ORDERS = tuple(permutations(METHODS))


def power_key():
    value = battery()
    return 'unknown' if value is None else 'ac' if value else 'battery'


def fraction_group(count, samples):
    if count == 0:
        return '0'
    if count*4 < samples:
        return '(0,25%)'
    if count*2 < samples:
        return '[25%,50%)'
    return '[50%,100%]'


def check_rows(requests, cfg):
    collectors = {method: Collector(method, cfg.samples, cfg.dimensions) for method in METHODS}
    for _, _, features, ids, weights, bias in requests:
        if not len(ids):
            continue
        rows = collectors[BASE].get(features, ids)
        labels = (rows @ weights.T + bias).argmax(1)
        for method in (ALLOCATE, REUSE):
            taken = collectors[method].get(features, ids)
            require(taken.flags.c_contiguous and taken.dtype == rows.dtype
                    and np.array_equal(taken, rows), f'{method} changed selected features')
            require(np.array_equal((taken @ weights.T + bias).argmax(1), labels),
                    f'{method} changed a scoring winner')


def replay(requests, cfg, method):
    by_shape = defaultdict(lambda: dict(seconds=0., gather_seconds=0., calls=0, endpoints=0))
    power_start, suspend_start = power_key(), suspend_clock()
    start = perf_counter()
    collector = Collector(method, cfg.samples, cfg.dimensions)
    setup = perf_counter()-start
    for _, _, features, ids, weights, bias in requests:
        if not len(ids):
            continue
        start = perf_counter()
        rows = collector.get(features, ids)
        gather = perf_counter()-start
        product = rows @ weights.T
        del rows
        scores = product + bias
        del product
        _ = scores.argmax(1)
        elapsed = perf_counter()-start
        key = features.shape[1], fraction_group(len(ids), cfg.samples)
        row = by_shape[key]
        row['seconds'] += elapsed
        row['gather_seconds'] += gather
        row['calls'] += 1
        row['endpoints'] += len(ids)
    power_end, suspend_end = power_key(), suspend_clock()
    power = {key: [power_start, power_end].count(key) for key in ('ac', 'battery', 'unknown')}
    suspended = None if None in (suspend_start, suspend_end) else max(0., suspend_end-suspend_start)
    return dict(seconds=setup + sum(row['seconds'] for row in by_shape.values()),
                scratch_bytes=collector.nbytes, setup_seconds=setup, power=power, suspend_seconds=suspended,
                strata=[dict(width=width, fraction=fraction, **row)
                        for (width, fraction), row in sorted(by_shape.items())])


def screen(cache, cfg, preset):
    requests = []
    collect = generator_factory(BASE, None, on_refresh=lambda *request: requests.append(request))
    with patch.object(fashion, 'generator', collect):
        audit = fashion.run(cache, cfg, BASE, audit=True)
    require(audit['comparisons'] == cfg.rounds * (cfg.samples//2) * len(cfg.dimensions),
            'Incomplete D audit against full B scoring')
    expected = [(rnd, c) for rnd in range(2, cfg.rounds+1) for c in range(len(cfg.dimensions))]
    require([(rnd, c) for rnd, c, *_ in requests] == expected, 'Incomplete refresh replay')
    check_rows(requests, cfg)
    blocks = []
    for repeat, order in enumerate(ORDERS if preset == 'full' else ORDERS[:1], 1):
        for attempt in range(2):
            runs = {method: replay(requests, cfg, method) for method in order}
            clean = eligible(runs, preset)
            blocks.append(dict(repeat=repeat, attempt=attempt, order=list(order), eligible=clean, runs=runs))
            if clean:
                break
    return dict(comparisons=audit['comparisons'], requests=len(requests), blocks=blocks,
                refreshed_by_client=audit['client_endpoints'])


def select(cells, preset):
    """Freeze one winner by seed-level wins, then by mean savings."""
    required = len(ORDERS) if preset == 'full' else 1
    summaries = []
    complete = True
    for cell, result in cells.items():
        eligible_blocks = [block['runs'] for block in result['blocks'] if block['eligible']]
        complete &= len(eligible_blocks) == required
        for method in (ALLOCATE, REUSE):
            baseline = mean(block[BASE]['seconds'] for block in eligible_blocks) if eligible_blocks else None
            candidate = mean(block[method]['seconds'] for block in eligible_blocks) if eligible_blocks else None
            savings = 100*(baseline-candidate)/baseline if baseline else None
            summaries.append(dict(cell=cell, candidate=method, eligible_blocks=len(eligible_blocks),
                                  baseline_seconds=baseline, candidate_seconds=candidate, saved_pct=savings,
                                  passed=len(eligible_blocks) == required and savings is not None
                                  and savings >= SCREEN_THRESHOLD))
    if not complete:
        return 'screen_incomplete', None, summaries
    if preset == 'smoke':
        return 'smoke_forced', REUSE, summaries
    ranking = []
    for method in (ALLOCATE, REUSE):
        rows = [r for r in summaries if r['candidate'] == method]
        wins = sum(r['passed'] for r in rows)
        if wins >= MIN_SCREEN_SEEDS:
            ranking.append((wins, mean(r['saved_pct'] for r in rows), method))
    if not ranking:
        return 'screen_failed', None, summaries
    # An exact tie favors the variant without retained scratch memory.
    winner = max(ranking, key=lambda row: (row[0], row[1], row[2] == ALLOCATE))[2]
    return 'screen_passed', winner, summaries
