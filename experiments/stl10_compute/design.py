"""Frozen design for the STL-10 step-2 B/E/D compute comparison."""
from dataclasses import replace

import numpy as np

from experiments.private_workload.design import Spec, spec_from_json  # noqa: F401  (re-exported for run.py)
from experiments.stl10_longrun.design import evaluate_trajectory
from experiments.stl10_transfer.design import plan as _transfer_plan

STEPS = 2
SEEDS = (1001, 1002, 1003)
SMOKE_SEEDS = (1001,)
PARTITIONS = ('iid', 'dirichlet_0.1')
METHODS = ('B', 'E', 'D')
ANCHORED_SEEDS = (1002, 1003)  # have longrun step-2 B trajectories


def plan(name, device=None):
    if name == 'full':
        config = _transfer_plan('full', device)[-1].config  # the M16384 spec
    else:
        config = _transfer_plan('smoke', device)[-1].config  # M128 fixture spec
    spec = Spec(config, 'fixed', STEPS, None)
    spec.validate()
    return [spec]


def schedule(name):
    seeds = SEEDS if name == 'full' else SMOKE_SEEDS
    spec = plan(name)[0]
    out = []
    i = 0
    for seed in seeds:
        for partition in PARTITIONS:
            order = METHODS[i % 3:] + METHODS[:i % 3]
            for position, method in enumerate(order):
                out.append(dict(seed=seed, partition=partition, case_id=spec.case_id,
                                method=method, triple=i, position=position))
            i += 1
    return out


def filename(meta):
    return f"{meta['partition']}_{meta['case_id']}_seed_{meta['seed']}_{meta['method']}.json"


def guardrail(b_record):
    """Apply the frozen longrun criteria to a transfer-style B record.

    The transfer engine evaluates on the 20-round grid only, so the
    checkpoints fed to the frozen evaluator are those rounds; early
    rounds 0-10 are unobserved in this experiment and S2 is judged on
    the 20-round grid (see PREREGISTRATION.md section 4).
    """
    checkpoints = []
    for entry in b_record['metrics']:
        clients = entry['clients']
        checkpoints.append(dict(
            round=entry['round'], clients=clients, mean=entry['mean'],
            single_cluster_clients=sum(c['occupied_clusters'] == 1 for c in clients),
            mean_largest_cluster_fraction=float(np.mean([c['largest_cluster_fraction'] for c in clients]))))
    adapted = dict(rounds=b_record['round_records'][-1]['round'], checkpoints=checkpoints,
                   round_records=b_record['round_records'])
    return evaluate_trajectory(adapted)
