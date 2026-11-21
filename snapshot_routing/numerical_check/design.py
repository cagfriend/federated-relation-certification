"""Deterministic binary64 fixtures for exact certification checks."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Fixture:
    name: str
    family: str
    features: np.ndarray
    edges: np.ndarray
    weights: np.ndarray
    biases: np.ndarray


def graph(samples):
    # Adjacent edges keep the witness readable. Pairing with both extreme
    # samples also exposes changed labels that adjacent relations can hide.
    path = [(i, i+1) for i in range(samples-1)]
    anchors = [(i, j) for i in range(samples) for j in (0, samples-1) if i != j]
    return np.asarray(sorted({tuple(sorted(pair)) for pair in path+anchors}), dtype=np.uint32)


def sequence(name, family, features, head, shifts):
    shifts = np.asarray(shifts, dtype=np.float64)
    weights = np.repeat(head[None, :, :], len(shifts), axis=0)
    biases = np.full((len(shifts), len(head)), -32., dtype=np.float64)
    biases[:, 0] = 0.
    biases[:, 1] = shifts
    return Fixture(name, family, features, graph(len(features)), weights, biases)


def near_tie(classes):
    offsets = np.asarray([-16,-4,-1,0,1,4,16], dtype=np.float64)
    ulp = np.spacing(1.)
    features = np.column_stack((1.+offsets*ulp, np.ones(len(offsets)), np.zeros(len(offsets))))
    # The two leading logits are x[0] and the class-one bias.
    head = np.zeros((classes, features.shape[1]), dtype=np.float64)
    head[0, 0] = 1.
    shift = 1.+np.array([-8,-2,-1,0,1,2,8,1,0,-1,-8])*ulp
    return sequence(f'near_tie_k{classes}', 'near_tie', features, head, shift)


def cancellation(exponent, width, order):
    large = 2.**exponent
    margins = np.asarray([-4.,-1.,-.25,0.,.25,1.,4.])
    features = np.zeros((len(margins), width), dtype=np.float64)
    common, small, negative = order
    features[:, common] = large
    features[:, negative] = -large
    features[:, small] = margins
    # Both classes carry the same cancelling terms. Class zero has a small
    # extra term. Moving its competitor's bias traverses the boundary.
    head = np.zeros((2, width), dtype=np.float64)
    head[:, [common, negative]] = 1.
    head[0, small] = 1.
    shifts = np.asarray([-2.,-.5,0.,.25,.5,1.,2.,.25,0.,-.5,-2.])
    suffix = 'middle' if common < small < negative else 'after'
    return sequence(f'cancellation_p{exponent}_d{width}_{suffix}', 'cancellation', features, head, shifts)


def long_prefix(exponent, steps):
    values = np.asarray([-4.,-1.,0.,.125,.25,.5,1.,1.5,2.,4.])
    features = np.column_stack((values, np.ones(len(values))))
    head = np.zeros((2, 2), dtype=np.float64)
    head[0, 0] = 1.
    huge = 2.**exponent
    past = [0., huge, -huge, huge, -huge, 0.]
    recent = [i/steps for i in range(1, 2*steps+1)]
    return sequence(f'prefix_p{exponent}_n{2*steps}', 'long_prefix', features, head, past+recent)


def fixtures(preset):
    grid = [
        near_tie(2),
        cancellation(53, 17, (0,1,2)),
        long_prefix(54, 16),
    ]
    if preset == 'full':
        grid.extend(near_tie(k) for k in (10,64))
        grid.extend(cancellation(exponent, width, order) for exponent, width, order in
                    [(40,17,(0,1,2)), (53,17,(0,2,1)), (53,64,(15,16,17)),
                     (60,64,(15,16,17)), (60,64,(15,17,16))])
        grid.extend(long_prefix(exponent, steps) for exponent, steps in [(40,128), (54,128), (60,512)])
    return grid
