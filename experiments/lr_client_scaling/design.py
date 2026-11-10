"""Frozen P3 fixed-per-client STL-10 client-count design."""
from dataclasses import replace

from experiments.private_workload.design import Spec
from experiments.stl10_compute.design import plan as compute_plan

METHODS = ('B', 'E', 'D')
PARTITIONS = ('iid', 'dirichlet_0.1')
CLIENTS = (2, 6, 12)
SMOKE_CLIENTS = (2, 4)
FULL_SEEDS = (1001, 1002, 1003)
SMOKE_SEEDS = (1001,)


def plan(preset_name, regime='fixed_per_client', device=None):
    if preset_name not in ('full', 'smoke'):
        raise ValueError(preset_name)
    if regime != 'fixed_per_client':
        raise ValueError('P3 supports fixed_per_client only')
    base = compute_plan(preset_name, device)[-1].config
    clients = CLIENTS if preset_name == 'full' else SMOKE_CLIENTS
    each = 400 if preset_name == 'full' else 32
    widths = (512, 2048) if preset_name == 'full' else (32, 64)
    specs = []
    for n in clients:
        dims = (widths[0],) * (n // 2) + (widths[1],) * (n - n // 2)
        cfg = replace(base, dimensions=dims, train_limit=base.public_pool + each * n,
                      public_weight=.5)
        spec = Spec(cfg, 'fixed', 2, None)
        spec.validate()
        specs.append(spec)
    return specs


def schedule(preset_name, regime='fixed_per_client', memory=False):
    if regime != 'fixed_per_client':
        raise ValueError('P3 supports fixed_per_client only')
    seeds = (1002,) if memory and preset_name == 'full' else ((1001,) if memory else (FULL_SEEDS if preset_name == 'full' else SMOKE_SEEDS))
    specs = plan(preset_name, regime)
    if memory:
        wanted = 12 if preset_name == 'full' else 4
        specs = [s for s in specs if len(s.config.dimensions) in (2, wanted)]
    out, block = [], 0
    for seed in seeds:
        for spec in specs:
            for partition in PARTITIONS:
                order = METHODS[block % 3:] + METHODS[:block % 3]
                for position, method in enumerate(order):
                    out.append(dict(seed=seed, partition=partition, regime=regime,
                                    clients=len(spec.config.dimensions), case_id=spec.case_id,
                                    method=method, block=block, position=position))
                block += 1
    return out


def filename(meta):
    return (f"{meta['regime']}_N{meta['clients']}_{meta['partition']}_"
            f"seed_{meta['seed']}_{meta['method']}.json")
