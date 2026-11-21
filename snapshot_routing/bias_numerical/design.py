"""Fixed original and held-out fixtures for the bias-change comparison."""

import numpy as np

from ..numerical_check.design import Fixture, cancellation, fixtures, graph, long_prefix, sequence


def held_out_bias_prefix(exponent, steps):
    base = long_prefix(exponent, steps)
    return Fixture(f"heldout_{base.name}", "heldout_bias_prefix",
                   base.features, base.edges, base.weights, base.biases)


def common_bias(exponent):
    common = 2. ** exponent
    spacing = np.spacing(common)
    features = np.array([-8., -2., -1., 0., 1., 2., 8.])[:, None] * spacing
    base = np.array([1., 1.5, 1., 1.5, 1., 1.5, 1., 1.5, 1.]) * common
    offsets = np.array([-4., -2., -1., 0., 1., 2., 4., 1., -2.]) * spacing
    biases = np.column_stack((base, base + offsets))
    weights = np.repeat(np.array([[[1.], [0.]]]), len(base), axis=0)
    return Fixture(f"heldout_common_bias_p{exponent}", "heldout_common_bias",
                   features, graph(len(features)), weights, biases)


def weight_prefix(exponent, steps):
    base = long_prefix(exponent, steps)
    weights = base.weights.copy()
    weights[:, 1, 1] = base.biases[:, 1]
    return Fixture(f"heldout_weight_{base.name}", "heldout_weight_prefix",
                   base.features, base.edges, weights, np.zeros_like(base.biases))


def mixed_cancellation(exponent, width, order):
    base = cancellation(exponent, width, order)
    large_bias = 2. ** 58
    shifts = np.concatenate(([0., large_bias, -large_bias, 0.], base.biases[:, 1]))
    return sequence(f"heldout_mixed_{base.name}", "heldout_mixed_cancellation",
                    base.features, base.weights[0], shifts)


def comparison_fixtures(preset):
    held_out = (
        held_out_bias_prefix(55, 24),
        held_out_bias_prefix(58, 96),
        common_bias(36),
        common_bias(48),
        weight_prefix(55, 24),
        weight_prefix(58, 96),
        mixed_cancellation(54, 17, (0, 1, 2)),
        mixed_cancellation(56, 33, (0, 2, 1)),
    )
    if preset == "smoke":
        held_out = held_out[::2]
    return [*fixtures(preset), *held_out]
