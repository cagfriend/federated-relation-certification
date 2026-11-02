"""Frozen design and mechanical criteria for the STL-10 repeat confirmation."""
import statistics as st

from experiments.private_workload.design import spec_from_json  # noqa: F401  (re-exported for run.py)
from experiments.stl10_compute.design import ANCHORED_SEEDS, METHODS, PARTITIONS, plan  # noqa: F401

REPEATS = 3
SEEDS = (1001, 1002, 1003)
SMOKE_SEEDS = (1001,)
C1_MAX_MEDIAN_RATIO_DB = 0.90
C2_MAX_MEDIAN_RATIO_DE = 1.00
C3_MIN_SEED_WINS = 2


def schedule(name):
    seeds = SEEDS if name == 'full' else SMOKE_SEEDS
    spec = plan(name)[0]
    out = []
    block = 0
    for seed in seeds:
        for partition in PARTITIONS:
            for repeat in range(REPEATS):
                order = METHODS[(block + repeat) % 3:] + METHODS[:(block + repeat) % 3]
                for position, method in enumerate(order):
                    out.append(dict(seed=seed, partition=partition, case_id=spec.case_id,
                                    method=method, repeat=repeat, block=block, position=position))
            block += 1
    return out


def filename(meta):
    return (f"{meta['partition']}_{meta['case_id']}_seed_{meta['seed']}_"
            f"{meta['method']}_rep{meta['repeat']}.json")


def _head(record):
    return record['summary'][record['method']]['head_pipeline_seconds']


def summarize(runs):
    """runs: list of (meta, record). Returns (noise rows, seed rows, partition verdicts)."""
    cells = {}
    by_repeat = {}
    for meta, record in runs:
        cells.setdefault((meta['partition'], meta['seed'], meta['method']), []).append(_head(record))
        key = (meta['partition'], meta['seed'], meta['method'], meta['repeat'])
        if key in by_repeat:
            raise ValueError('Duplicate repeat in summary')
        by_repeat[key] = _head(record)
    noise = []
    for (part, seed, method), values in sorted(cells.items()):
        mean = st.fmean(values)
        noise.append(dict(partition=part, seed=seed, method=method, repeats=len(values),
                          mean_head_seconds=mean, min_head_seconds=min(values),
                          max_head_seconds=max(values),
                          relative_range=(max(values) - min(values)) / mean if mean else None))
    seed_rows = []
    for part in PARTITIONS:
        for seed in sorted({s for (p, s, m) in cells if p == part}):
            means = {m: st.fmean(cells[part, seed, m]) for m in METHODS}
            ratios_db = [by_repeat[part, seed, 'D', r] / by_repeat[part, seed, 'B', r] for r in range(REPEATS)]
            ratios_de = [by_repeat[part, seed, 'D', r] / by_repeat[part, seed, 'E', r] for r in range(REPEATS)]
            seed_rows.append(dict(partition=part, seed=seed,
                                  B_mean=means['B'], E_mean=means['E'], D_mean=means['D'],
                                  repeat_ratio_DB_min=min(ratios_db), repeat_ratio_DB_max=max(ratios_db),
                                  repeat_ratio_DE_min=min(ratios_de), repeat_ratio_DE_max=max(ratios_de),
                                  ratio_DB=means['D'] / means['B'], ratio_DE=means['D'] / means['E'],
                                  saved_DB=means['B'] - means['D'], saved_DE=means['E'] - means['D'],
                                  win_B=means['D'] < means['B'], win_E=means['D'] < means['E']))
    verdicts = {}
    for part in PARTITIONS:
        rows = [r for r in seed_rows if r['partition'] == part]
        if not rows:
            continue
        median_db = st.median(r['ratio_DB'] for r in rows)
        median_de = st.median(r['ratio_DE'] for r in rows)
        c1 = median_db <= C1_MAX_MEDIAN_RATIO_DB
        c2 = median_de < C2_MAX_MEDIAN_RATIO_DE
        c3 = sum(r['win_B'] for r in rows) >= C3_MIN_SEED_WINS and sum(r['win_E'] for r in rows) >= C3_MIN_SEED_WINS
        verdicts[part] = dict(median_ratio_DB=median_db, median_ratio_DE=median_de,
                              wins_B=sum(r['win_B'] for r in rows), wins_E=sum(r['win_E'] for r in rows),
                              C1=bool(c1), C2=bool(c2), C3=bool(c3), confirmed=bool(c1 and c2 and c3))
    return noise, seed_rows, verdicts
