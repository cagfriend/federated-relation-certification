"""Frozen confirmation design: new seeds, independent processes, repeats.

Implements docs/NEXT_EXPERIMENTS.md item 2 as preregistered in
PREREGISTRATION.md. The training implementation is reused unchanged from
experiments.private_workload; only the execution protocol differs
(one method per process, two technical repeats, balanced order).
"""
from dataclasses import replace
from experiments.private_workload.design import PARTITIONS, METHODS, QUALITY_ACC_DROP
from experiments.private_workload.design import Spec, spec_from_json
from experiments.private_workload.design import plan as _workload_plan

# New seeds, never used by any earlier experiment in this repository
# (earlier lines used 101/202/303 and 404/505/606).
CONFIRM_SEEDS = (707, 808, 909)
SMOKE_SEEDS = (707,)
REPEATS = (0, 1)
PRIMARY_PRIVATE_LIMIT = 2048
SMOKE_PRIMARY_LIMIT = 128
# Tiers: the frozen candidate plus the full reference (guardrail baseline).
FORMAL_LIMITS = (None, PRIMARY_PRIVATE_LIMIT)
SMOKE_LIMITS = (None, SMOKE_PRIMARY_LIMIT)

# Preregistered decision rules for the candidate tier, per partition.
DECISION = dict(
    db_head_ratio_median_max=0.90,   # C1
    de_head_ratio_median_max=1.00,   # C2 (strictly below)
    min_seed_wins=2,                 # C3, out of len(CONFIRM_SEEDS)
)


def plan(name, device=None):
    """Confirmation specs: same frozen config as private_workload."""
    specs = _workload_plan(name, device)
    limits = FORMAL_LIMITS if name == 'full' else SMOKE_LIMITS
    keep = [s for s in specs if s.private_limit in limits]
    if len(keep) != len(limits):
        raise AssertionError('Confirmation tiers differ from preregistration')
    return keep


def seeds_for(name):
    return CONFIRM_SEEDS if name == 'full' else SMOKE_SEEDS


def method_order(triple_index):
    """Balanced rotation: each method leads equally often across triples."""
    order = list(METHODS)
    shift = triple_index % len(order)
    return tuple(order[shift:] + order[:shift])


def schedule(name):
    """Deterministic run list. A triple is (partition, seed, tier, repeat):
    its three method runs execute consecutively in the rotated order."""
    specs = plan(name)
    runs = []
    triple = 0
    for seed in seeds_for(name):
        for part in PARTITIONS:
            for spec in specs:
                for repeat in REPEATS:
                    for position, method in enumerate(method_order(triple)):
                        runs.append(dict(partition=part, seed=seed, case_id=spec.case_id,
                                         method=method, repeat=repeat, triple=triple,
                                         position=position))
                    triple += 1
    return runs


def run_filename(run):
    return (f"{run['partition']}_{run['case_id']}_seed_{run['seed']}_"
            f"{run['method']}_rep{run['repeat']}.json")
