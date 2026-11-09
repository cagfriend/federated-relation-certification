import statistics
from experiments.lr_compute.design import plan as p1_plan, schedule as p1_schedule

METHODS = ('B', 'E', 'D')
REPEATS = 3
FULL_CASES = ('n12_k10_dirichlet_0.1_seed1001', 'n12_k10_dirichlet_0.1_seed1101',
              'n6_k64_dirichlet_0.1_seed1002', 'n6_k64_dirichlet_0.1_seed1101')
SMOKE_CASES = ('n12_k10_dirichlet_0.1_seed1001', 'n6_k64_dirichlet_0.1_seed1001')


def plan(preset):
    selected = FULL_CASES if preset == 'full' else SMOKE_CASES
    full = p1_plan(preset)
    return {cid: full[cid] for cid in selected}


def schedule(preset):
    originals = {m['case_id']: m for m in p1_schedule(preset) if m['method'] == 'B'}
    jobs = []
    for cid in plan(preset):
        base = {k: v for k, v in originals[cid].items() if k not in ('method', 'block', 'position')}
        for repeat in range(REPEATS):
            order = METHODS[repeat:] + METHODS[:repeat]
            for position, method in enumerate(order):
                jobs.append(dict(base, repeat=repeat, method=method, position=position))
    return jobs


def filename(meta):
    return f"{meta['case_id']}_r{meta['repeat']}_{meta['method']}.json"


def criteria(ratios_b, ratios_e):
    if len(ratios_b) != REPEATS or len(ratios_e) != REPEATS:
        raise ValueError('Need exactly three paired repetitions')
    c1 = statistics.median(ratios_b) <= .90
    c2 = statistics.median(ratios_e) <= .97
    c3 = sum(v < 1 for v in ratios_b) >= 2 and sum(v < 1 for v in ratios_e) >= 2
    return dict(C1=c1, C2=c2, C3=c3, passed=c1 and c2 and c3)
