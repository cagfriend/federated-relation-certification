from dataclasses import replace
from experiments.quantity_heterogeneity.design import plan as quantity_plan

BRANCHES=('baseline','private_only','low_lr')
PROBE_STREAM=7901
PROBE_SIZES={'full':512,'smoke':32}
PLAN_COMMIT='8f8e7554ea7877eca0e7259a4f043dc80ca87aaf'


def plan(preset):
    if preset not in ('full','smoke'):raise ValueError(preset)
    base=quantity_plan(preset)['strong']
    return {branch:replace(base,config=replace(base.config,
            rounds=(40 if branch=='baseline' else 200) if preset=='full' else (2 if branch=='baseline' else 3),
            public_weight=.125 if branch=='low_lr' else .5)) for branch in BRANCHES}


def cases(preset):
    if preset not in ('full','smoke'):raise ValueError(preset)
    return [dict(case_id=f'strong_{part}_seed{seed}',seed=seed,partition=part,profile='strong',method='B',clients=6)
            for seed in ((1001,1002) if preset=='full' else (1001,))
            for part in ('iid','dirichlet_0.1')]


def schedule(preset):
    # Every baseline must pass before the first long diagnostic is started.
    return [dict(case,branch=branch) for branch in BRANCHES for case in cases(preset)]


def filename(meta):return f"{meta['case_id']}_{meta['branch']}.json"


def source_key(meta):return f"{meta['seed']}|{meta['partition']}|strong"
