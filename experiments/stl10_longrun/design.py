"""Frozen design and mechanical criteria for the STL-10 long-horizon validation."""
from dataclasses import replace

from experiments.private_workload.design import Spec, spec_from_json  # noqa: F401  (spec_from_json re-exported for run.py)
from experiments.stl10_transfer.design import plan as _transfer_plan

STEPS = (1, 2)
SEEDS = (1002, 1003)
SMOKE_SEEDS = (1001,)
PARTITIONS = ('iid', 'dirichlet_0.1')
METHOD = 'B'
SMOKE_ROUNDS = 12

# Operational acceptance thresholds, fixed before any run (PREREGISTRATION.md
# section 4). They are pre-specified operating standards, not theoretical
# healthy-clustering bounds and not calibrated statistical thresholds.
S1_MAX_MEAN_LARGEST = 0.60
S1_CLIENT_LARGEST_LT = 0.99
S2_MAX_SINGLE_CLIENTS = 2
S2_MEAN_LARGEST_LT = 0.90
S2_FROM_ROUND = 20
Q1_MIN_ACC = 0.14
Q1_MIN_NMI = 0.01
Q2_MAX_FINAL_EDGE_FRACTION = 0.60


def checkpoints(rounds):
    """Evaluation rounds: 0,1,2,5,10, every 20, and the final round."""
    points = {0, 1, 2, 5, 10, rounds}
    points.update(range(20, rounds + 1, 20))
    return sorted(p for p in points if 0 <= p <= rounds)


def plan(name, device=None):
    if name == 'full':
        config = _transfer_plan('full', device)[-1].config  # the M16384 spec
        seeds = SEEDS
    else:
        config = replace(_transfer_plan('smoke', device)[-1].config, rounds=SMOKE_ROUNDS)
        seeds = SMOKE_SEEDS
    specs = [Spec(config, 'fixed', steps, None) for steps in STEPS]
    for spec in specs:
        spec.validate()
    if len({str(spec.config.preparation()) for spec in specs}) != 1:
        raise AssertionError('Preparation changed across public-step tiers')
    return specs


def schedule(name):
    seeds = SEEDS if name == 'full' else SMOKE_SEEDS
    out = []
    for seed in seeds:
        for partition in PARTITIONS:
            for spec in plan(name):
                out.append(dict(seed=seed, partition=partition, case_id=spec.case_id,
                                steps=spec.steps, method=METHOD))
    return out


def filename(meta):
    return f"{meta['partition']}_{meta['case_id']}_seed_{meta['seed']}_B.json"


def evaluate_trajectory(record):
    """Mechanical S1/S2/Q1/Q2 verdict for one finished run record."""
    by_round = {c['round']: c for c in record['checkpoints']}
    final = by_round[record['rounds']]
    s1 = (final['single_cluster_clients'] == 0
          and all(c['largest_cluster_fraction'] < S1_CLIENT_LARGEST_LT for c in final['clients'])
          and final['mean_largest_cluster_fraction'] <= S1_MAX_MEAN_LARGEST)
    judged = [c for c in record['checkpoints'] if c['round'] >= S2_FROM_ROUND]
    s2 = all(c['single_cluster_clients'] <= S2_MAX_SINGLE_CLIENTS
             and c['mean_largest_cluster_fraction'] < S2_MEAN_LARGEST_LT for c in judged)
    q1 = final['mean']['acc'] >= Q1_MIN_ACC and final['mean']['nmi'] >= Q1_MIN_NMI
    q2 = record['round_records'][-1]['positive_relation_fraction'] <= Q2_MAX_FINAL_EDGE_FRACTION
    result = dict(S1=bool(s1), S2=bool(s2), Q1=bool(q1), Q2=bool(q2))
    result['passed'] = all(result.values())
    return result


def select_tier(passed_by_steps):
    """Frozen selection rule: 2 steps if fully validated, else 1, else None.

    passed_by_steps maps each step tier to the list of per-trajectory
    pass booleans; a tier is validated only when every trajectory passed.
    """
    if passed_by_steps.get(2) and all(passed_by_steps[2]):
        return 2
    if passed_by_steps.get(1) and all(passed_by_steps[1]):
        return 1
    return None
