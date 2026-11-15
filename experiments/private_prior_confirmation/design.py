"""Frozen design for private-prior exact-trajectory confirmation repeats."""

from dataclasses import replace

from experiments.quantity_heterogeneity.design import plan as quantity_plan

SEEDS = (1201, 1202, 1203)
SMOKE_SEEDS = (1201,)
PARTITIONS = ('iid', 'dirichlet_0.1')
METHODS = ('B', 'E', 'D')
REPEAT_ORDERS = ('BED', 'EDB', 'DBE')


def spec(preset, device=None):
    """Return the existing strong-quantity spec, varying only prepare_device."""
    if preset not in ('full', 'smoke'):
        raise ValueError(f'Unknown preset: {preset}')
    base = quantity_plan(preset, device)['strong']
    if preset == 'smoke':
        base = replace(base, config=replace(base.config, rounds=3, eval_every=3))
        base.validate()
    return base


def cases(preset='full'):
    if preset == 'full':
        seeds, partitions = SEEDS, PARTITIONS
    elif preset == 'smoke':
        seeds, partitions = SMOKE_SEEDS, ('iid',)
    else:
        raise ValueError(f'Unknown preset: {preset}')
    return tuple(dict(seed=seed, partition=partition,
                      case_id=f"strong_{partition}_seed{seed}")
                 for seed in seeds for partition in partitions)


# Public full-design case inventory retained for callers that need to validate
# the formal scope without constructing a schedule.
CASES = cases('full')


def schedule(preset='full'):
    """List all runs in single-process order, with three technical repeats.

    Each repeat is a complete B/E/D block. The block order rotates BED, EDB,
    DBE across repeats, so every case-method pair has exactly three runs and
    is first-run once within each repeated block.
    """
    result = []
    for case_index, case in enumerate(cases(preset)):
        for repeat, order in enumerate(REPEAT_ORDERS):
            for position, method in enumerate(order):
                result.append(dict(case, method=method, repeat=repeat,
                                   block=case_index * len(REPEAT_ORDERS) + repeat,
                                   position=position, memory=False))
    return result


def filename(meta):
    return f"{meta['case_id']}_{meta['method']}_repeat{meta['repeat']}.json"
