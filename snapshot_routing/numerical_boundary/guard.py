"""Experimental guards for cumulative weight rounding and shape-sensitive scoring."""

import numpy as np

from experiments.public_scaling.certification import hard_relations
from experiments.public_scaling.endpoint_bias import EndpointBiasGenerator


class GuardedGenerator(EndpointBiasGenerator):
    def __init__(self, features, weights, bias, edges, *, interval, dense):
        super().__init__(features, weights, bias, edges)
        self.interval = interval
        self.dense = dense
        self.fallback = ''
        self.scale_rounds = self.rebuild_rounds = 0
        if interval:
            self.weight_lower = np.zeros_like(self.weight_prefix)
        if dense:
            self.feature_scale = float(np.max(np.abs(features), initial=0.))
            self.risky_previous = self.risky(weights, bias)

    def risky(self, weights, bias):
        # One head-level scale check. Ambiguous large scores use the exact
        # same matrix shape and tie rule as B, including a clean recovery round.
        with np.errstate(over='ignore', invalid='ignore'):
            magnitude = self.feature_scale * np.abs(weights).sum(1).max() + np.abs(bias).max()
            allowance = 8 * np.finfo(np.float64).eps * (self.dimension + 2) * magnitude
        return not np.isfinite(allowance) or allowance >= 1e-10

    def _advance(self, weights, bias):
        if not self.interval:
            return super()._advance(weights, bias)
        delta_w = weights - self.previous_weights
        movement = np.linalg.norm(delta_w[:, None, :] - delta_w[None, :, :], axis=2)
        active = movement != 0.
        # Bracket the cumulative sum of the computed movement increments.
        # At refresh, cache the lower end. A later upper minus lower is
        # conservative for this sum even when tiny increments were absorbed.
        lower = self.weight_lower + movement
        upper = self.weight_prefix + movement
        np.nextafter(lower, -np.inf, out=self.weight_lower, where=active)
        np.nextafter(upper, np.inf, out=self.weight_prefix, where=active)
        np.subtract(bias[None, :], bias[:, None], out=self.bias_prefix)
        self.previous_weights = weights.copy()

    def _refresh(self, ids, weights, bias):
        super()._refresh(ids, weights, bias)
        if self.interval:
            self.weight_at[ids] = self.weight_lower[self.winners[ids]]

    def candidate_matrix(self):
        if not self.interval:
            return super().candidate_matrix()
        movement = self.weight_prefix[self.winners] - self.weight_at
        np.nextafter(movement, np.inf, out=movement, where=movement > 0.)
        bias = self.bias_prefix[self.winners] - self.bias_at
        bound = self.radius[:, None] * movement + bias
        bound += 1e-10 * (1 + np.abs(bound) + np.abs(self.gaps))
        return self.gaps <= bound

    def generate(self, weights, bias):
        self.fallback = ''
        if self.dense:
            risky = self.risky(weights, bias)
            self.fallback = 'scale' if risky else 'rebuild' if self.risky_previous else ''
            self.risky_previous = risky
        if not self.fallback:
            return super().generate(weights, bias)

        self.scale_rounds += self.fallback == 'scale'
        self.rebuild_rounds += self.fallback == 'rebuild'
        self.round += 1
        self._advance(weights, bias)
        scores = self.features @ weights.T + bias
        if not np.isfinite(scores).all():
            raise ArithmeticError('Non-finite dense scores')
        self.winners[:] = scores.argmax(1)
        self.gaps[:] = scores[np.arange(self.samples), self.winners, None] - scores
        weight_reference = self.weight_lower if self.interval else self.weight_prefix
        self.weight_at[:] = weight_reference[self.winners]
        self.bias_at[:] = self.bias_prefix[self.winners]
        self.last_evaluated.fill(self.round)
        return hard_relations(self.winners, self.edges), {'forward_endpoints': self.samples}
