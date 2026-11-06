from dataclasses import replace
import math
from experiments.client_scaling.design import plan as n_plan


def spec_for(preset, family, device=None):
    if family not in ('n12_k10', 'n6_k64'):
        raise ValueError('Unknown family')
    if preset == 'full':
        n = 12 if family == 'n12_k10' else 6
        spec = next(s for s in n_plan('full', device=device) if len(s.config.dimensions) == n)
    elif preset == 'smoke':
        spec = n_plan('smoke')[0]
        spec = replace(spec, config=replace(spec.config, rounds=12))
    else:
        raise ValueError('Unknown preset')
    spec = replace(spec, config=replace(spec.config, classes=10 if family == 'n12_k10' else 64))
    spec.validate()
    return spec


def cases(preset):
    out = []
    for family in ('n12_k10', 'n6_k64'):
        values = [(1001, 'dirichlet_0.1', 'healthy'),
                  (1003 if family == 'n12_k10' else 1002, 'dirichlet_0.1', 'known_failure'),
                  (1101, 'iid', 'new_seed'), (1101, 'dirichlet_0.1', 'new_seed')]
        if preset == 'smoke':
            values = [(1001, p, 'development') for p in ('iid', 'dirichlet_0.1')]
        for seed, partition, role in values:
            out.append(dict(family=family, seed=seed, partition=partition, role=role,
                            case_id=f'{family}_{partition}_seed{seed}'))
    return out


def verdict(record):
    metrics = record['metrics']
    last = metrics[-1]
    clients = last['clients']
    final_structure = (all(c['occupied_clusters'] > 1 and c['largest_cluster_fraction'] < .99 for c in clients)
                       and sum(c['largest_cluster_fraction'] for c in clients) / len(clients) <= .60)
    observed = [m for m in metrics if m['round'] >= 20]
    process = all(sum(c['largest_cluster_fraction'] for c in m['clients']) / len(m['clients']) < .90
                  and sum(c['largest_cluster_fraction'] >= .99 for c in m['clients']) <= math.ceil(len(m['clients']) / 3)
                  for m in observed)
    information = last['mean']['nmi'] >= .01
    return dict(final_structure=final_structure, process=process, nmi_floor=information,
                process_checkpoints=len(observed), passed=final_structure and process and information)
