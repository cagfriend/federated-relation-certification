"""Frozen remaining cases for local public-LR confirmation."""
from dataclasses import replace

from experiments.local_public_lr.design import public_client_weights
from experiments.quantity_heterogeneity.design import plan as quantity_plan

BRANCHES = ('local_lr',)
METHODS = ('B',)
PLAN_COMMIT = 'e3dce2b4a9c02a81310e550d81e6e5fe16bace67'
FULL_CASES = (
    dict(seed=1001, partition='dirichlet_0.1'),
    dict(seed=1002, partition='iid'),
    dict(seed=1002, partition='dirichlet_0.1'),
)
SMOKE_CASES = FULL_CASES


def cases(preset):
    if preset not in ('full', 'smoke'):
        raise ValueError(preset)
    return [dict(case_id=f"strong_{item['partition']}_seed{item['seed']}",
                 **item, profile='strong', method='B')
            for item in (FULL_CASES if preset == 'full' else SMOKE_CASES)]


def plan(preset):
    if preset not in ('full', 'smoke'):
        raise ValueError(preset)
    base = quantity_plan(preset)['strong']
    cfg = replace(base.config, rounds=200 if preset == 'full' else 3,
                  eval_every=20 if preset == 'full' else 1, public_weight=.5)
    spec = replace(base, config=cfg)
    return {'local_lr': spec}


def schedule(preset):
    return [dict(case, branch='local_lr') for case in cases(preset)]


def filename(meta):
    return f"{meta['case_id']}_{meta['branch']}.json"


def input_key(meta):
    return f"{meta['seed']}|{meta['partition']}|strong"


def client_weights(branch='local_lr'):
    return public_client_weights(branch, 6)
