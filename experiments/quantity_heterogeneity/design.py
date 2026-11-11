"""Frozen quantity profiles and paired B/E/D run schedule."""
from dataclasses import replace

from experiments.private_workload.design import Spec
from experiments.stl10_compute.design import plan as compute_plan

PROFILES = ('equal', 'moderate', 'strong')
PROFILE_REGIME = {p: f'quantity_{p}' for p in PROFILES}
SEEDS = (1001, 1002, 1003)
SMOKE_SEEDS = (1001,)
PARTITIONS = ('iid', 'dirichlet_0.1')
METHODS = ('B', 'E', 'D')


def capacities(preset, profile):
    if profile not in PROFILES:
        raise ValueError(f'Unknown quantity profile: {profile}')
    if preset == 'full':
        base = {'equal': (400,) * 6,
                'moderate': (200, 400, 600, 200, 400, 600),
                'strong': (100, 400, 700, 100, 400, 700)}[profile]
    elif preset == 'smoke':
        base = {'equal': (32,) * 6,
                'moderate': (16, 32, 48, 16, 32, 48),
                'strong': (10, 32, 54, 10, 32, 54)}[profile]
    else:
        raise ValueError(f'Unknown preset: {preset}')
    return base


def plan(preset, device=None):
    if preset not in ('full', 'smoke'):
        raise ValueError(f'Unknown preset: {preset}')
    cfg = compute_plan(preset, device)[0].config
    dimensions = cfg.dimensions if preset == 'full' else (32, 32, 32, 64, 64, 64)
    cfg = replace(cfg, dimensions=dimensions, samples=cfg.public_pool, degree=1,
                  public_epochs=1, public_weight=0.5, head_lr=0.1)
    result = {}
    for profile in PROFILES:
        c = capacities(preset, profile)
        if sum(c) != (2400 if preset == 'full' else 192):
            raise AssertionError('Private capacity total differs from preregistration')
        profile_cfg = replace(cfg, train_limit=cfg.public_pool + sum(c))
        spec = Spec(profile_cfg, 'fixed', 2, None)
        spec.validate()
        result[profile] = spec
    if preset == 'full':
        from experiments.lr_client_scaling.design import plan as p3_plan
        p3_equal = p3_plan('full', 'fixed_per_client', device)[1]
        if result['equal'].json() != p3_equal.json():
            raise AssertionError('Full equal profile must exactly match P3 N6 configuration')
    return result


def schedule(preset, memory=False):
    specs = plan(preset)
    seeds = SEEDS if preset == 'full' else SMOKE_SEEDS
    out, block = [], 0
    for seed in seeds:
        for partition in PARTITIONS:
            for profile in PROFILES:
                if memory and (profile != 'strong' or seed != (1002 if preset == 'full' else 1001)):
                    continue
                spec = specs[profile]
                order = METHODS[block % 3:] + METHODS[:block % 3]
                for position, method in enumerate(order):
                    out.append(dict(seed=seed, partition=partition, profile=profile,
                                    regime=PROFILE_REGIME[profile], clients=6, case_id=spec.case_id,
                                    method=method, block=block, position=position))
                block += 1
    return out


def filename(meta):
    return f"{meta['partition']}_{meta['profile']}_seed{meta['seed']}_{meta['method']}.json"


def input_key(meta):
    return f"{meta['seed']}|{meta['partition']}|{meta['profile']}"
