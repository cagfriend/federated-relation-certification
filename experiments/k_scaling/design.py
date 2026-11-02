from dataclasses import replace
from experiments.stl10_compute.design import plan as base_plan

KS = (10, 16, 32, 64)
SEEDS = (1001, 1002, 1003)
PARTITIONS = ('iid', 'dirichlet_0.1')
METHODS = ('B', 'E', 'D')

def plan(preset):
    base = base_plan(preset)[0]
    values = KS if preset == 'full' else (10, 16, 64)
    out = [replace(base, config=replace(base.config, classes=k)) for k in values]
    for spec in out: spec.validate()
    return out

def filename(meta):
    return f"{meta['partition']}_k{meta['classes']}_seed{meta['seed']}_{meta['method']}.json"

def schedule(preset, memory=False):
    out = []; block = 0
    for seed in (SEEDS if preset == 'full' else (1001,)):
        for part in PARTITIONS:
            for spec in plan(preset):
                if memory and (seed != (1002 if preset == 'full' else 1001) or spec.config.classes not in (10,64)): continue
                order = METHODS[block % 3:] + METHODS[:block % 3]
                for pos,m in enumerate(order):
                    out.append(dict(seed=seed, partition=part, classes=spec.config.classes, method=m, block=block, position=pos))
                block += 1
    return out
