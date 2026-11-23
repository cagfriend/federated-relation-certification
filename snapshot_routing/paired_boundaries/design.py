"""Frozen size screening and independent M4096 confirmation."""

from collections import Counter

from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_graph_scaling.design import SIZES, cell_id
from ..confirmation.run import PARTITIONS, SEEDS

METHODS = ('B', 'E', 'D', 'Demand')
FRESH_SEEDS = (2024, 2025, 2026)
# A balanced Latin square. Every position and directed adjacent pair
# appears once per cell over the four blocks.
ORDERS = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))


def schedule(preset):
    historical = [
        dict(seed=seed, partition=part, public_size=size)
        for seed in (SEEDS if preset == 'full' else SEEDS[:1])
        for part in PARTITIONS
        for size in SIZES['full' if preset == 'full' else 'smoke']
    ]
    fresh = [dict(seed=seed, partition=part, public_size=4096 if preset == 'full' else 128)
             for seed in (FRESH_SEEDS if preset == 'full' else FRESH_SEEDS[:1])
             for part in PARTITIONS]
    if preset == 'smoke':
        historical = [case for case in historical if case['public_size'] in (32, 128)]
        fresh = []
    if preset == 'fresh-smoke':
        historical = []
    cases = historical + fresh
    blocks = []
    for repeat in range(4 if preset == 'full' else 1):
        for offset in range(len(cases)):
            index = (offset+repeat) % len(cases)
            order = [METHODS[k] for k in ORDERS[(index+repeat) % 4]]
            blocks.append(dict(case=cases[index], repeat=repeat+1, order=order))
    if preset == 'full':
        positions = Counter((cell_id(b['case']), m, j) for b in blocks for j, m in enumerate(b['order']))
        require(len(cases) == 24 and len(blocks) == 96 and len(positions) == 384
                and set(positions.values()) == {1}, 'Unbalanced timing design')
    return cases, fresh, blocks
