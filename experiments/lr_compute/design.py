from dataclasses import replace
from experiments.public_lr_confirmation.design import cases, spec_for

METHODS = ('B', 'E', 'D')


def plan(preset):
    return {c['case_id']: replace(spec_for(preset, c['family']),
                                config=replace(spec_for(preset, c['family']).config, public_weight=.5))
            for c in cases(preset)}


def schedule(preset, memory=False):
    matrix = cases(preset)
    if memory:
        if preset == 'full':
            selected = {'n12_k10_dirichlet_0.1_seed1001', 'n6_k64_dirichlet_0.1_seed1002'}
        else:
            selected = {'n12_k10_dirichlet_0.1_seed1001', 'n6_k64_dirichlet_0.1_seed1001'}
        matrix = [c for c in matrix if c['case_id'] in selected]
    jobs = []
    for block, case in enumerate(matrix):
        order = METHODS[block % 3:] + METHODS[:block % 3]
        for position, method in enumerate(order):
            jobs.append(dict(case, method=method, block=block, position=position))
    return jobs


def filename(meta):
    return f"{meta['case_id']}_{meta['method']}.json"
