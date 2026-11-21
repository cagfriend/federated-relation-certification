"""Experimental relation generator with endpoint-relative bias changes."""

import numpy as np

from experiments.public_scaling.certification import RelationGenerator


class EndpointBiasGenerator(RelationGenerator):
    """Use signed rival-minus-winner bias changes while retaining the weight bound."""

    def __init__(self, features, weights, bias, edges):
        super().__init__(features, weights, bias, edges, "relation")
        # The inherited candidate/refresh code reads this table and its cached rows.
        # Here the table holds the current class-pair offset, with no history sum.
        np.subtract(bias[None, :], bias[:, None], out=self.bias_prefix)
        np.take(self.bias_prefix, self.winners, axis=0, out=self.bias_at, mode="clip")
        del self.previous_bias

    def _advance(self, weights, bias):
        delta_w = weights - self.previous_weights
        pair_delta = delta_w[:, None, :] - delta_w[None, :, :]
        self.weight_prefix += np.linalg.norm(pair_delta, axis=2)
        np.subtract(bias[None, :], bias[:, None], out=self.bias_prefix)
        self.previous_weights = weights.copy()
