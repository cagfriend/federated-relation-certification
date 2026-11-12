from dataclasses import replace
from experiments.quantity_heterogeneity.design import plan as quantity_plan

BRANCHES = ('baseline', 'local_lr')
PROBE_STREAM = 7901
PROBE_SIZES = {'full': 512, 'smoke': 32}
PLAN_COMMIT = 'local-public-lr-v1-20261112'


def public_client_weights(branch, clients=6):
    if branch not in BRANCHES or clients != 6:
        raise ValueError((branch, clients))
    return [.125 if branch == 'local_lr' and c in (0, 3) else .5 for c in range(clients)]


def plan(preset):
    if preset not in ('full', 'smoke'):
        raise ValueError(preset)
    base = quantity_plan(preset)['strong']
    spec = replace(base, config=replace(base.config, rounds=200 if preset == 'full' else 3,
                                       eval_every=20 if preset == 'full' else 1, public_weight=.5))
    return {branch: spec for branch in BRANCHES}


def cases(preset):
    plan(preset)
    return [dict(case_id='strong_iid_seed1001', seed=1001, partition='iid', profile='strong', method='B', clients=6)]


def schedule(preset):
    return [dict(case, branch=branch) for branch in BRANCHES for case in cases(preset)]


def filename(meta):
    return f"{meta['case_id']}_{meta['branch']}.json"


def source_key(meta):
    return f"{meta['seed']}|{meta['partition']}|strong"
