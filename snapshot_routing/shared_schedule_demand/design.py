"""The E54 M4096 cells and a complete balance of three-method orders."""

from itertools import permutations

from ..paired_boundaries.design import schedule as e54_schedule
from .worker import METHODS

ORDERS = tuple(permutations(METHODS))
HEAD_MARGIN_PCT = 3.
MIN_WINS = 4


def schedule(preset):
    cases, fresh, _ = e54_schedule('full' if preset == 'full' else 'fresh-smoke')
    cases = [case for case in cases if case['public_size'] == (4096 if preset == 'full' else 128)]
    fresh = [case for case in fresh if case in cases]
    blocks = []
    for repeat in range(len(ORDERS) if preset == 'full' else 1):
        for offset in range(len(cases)):
            index = (offset+repeat) % len(cases)
            order = ORDERS[(index+repeat) % len(ORDERS)]
            blocks.append(dict(case=cases[index], repeat=repeat+1, order=list(order)))
    return cases, fresh, blocks
