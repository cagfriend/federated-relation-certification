"""Choose one path before evaluation; both paths use the same cache object."""
from time import perf_counter

from experiments.public_scaling.certification import RelationGenerator

POLICIES = ('E', 'D', 'static', 'adaptive')
# Exploratory rule, frozen before this experiment. Not a fitted cost model.
RULE = {'version': 1, 'static_D_max_degree': 1,
        'refresh_threshold_at_width_2048_degree_1': 0.15,
        'width_reference': 2048,
        'adaptive_condition': 'last_refresh_fraction * degree <= 0.15 * width / 2048',
        'first_post_bootstrap': 'static', 'timing_feedback': False}


def choose(policy, degree, width, last_fraction):
    if policy in ('E', 'D'):
        return policy
    static = 'D' if degree <= RULE['static_D_max_degree'] else 'E'
    if policy == 'static' or last_fraction is None:
        return static
    if policy != 'adaptive':
        raise ValueError('Unknown policy')
    threshold = RULE['refresh_threshold_at_width_2048_degree_1'] * width / RULE['width_reference']
    return 'D' if last_fraction * degree <= threshold else 'E'


class PolicyGenerator(RelationGenerator):
    def __init__(self, features, weights, bias, edges, policy, degree, **kwargs):
        if policy not in POLICIES or degree < 1:
            raise ValueError('Invalid selection policy or degree')
        self.policy, self.degree = policy, degree
        self.last_fraction = None
        self.last_path = None
        self.switches = 0
        path = choose(policy, degree, features.shape[1], None)
        super().__init__(features, weights, bias, edges,
                         'point' if path == 'E' else 'relation', **kwargs)

    def generate(self, weights, bias):
        # Includes input packing, choice, mode assignment and policy bookkeeping
        # in the caller's generation timer. No candidate matrix/forward probe.
        previous = self.last_fraction
        t = perf_counter()
        path = choose(self.policy, self.degree, self.dimension, previous)
        switched = self.last_path is not None and path != self.last_path
        self.mode = 'point' if path == 'E' else 'relation'
        decision_seconds = perf_counter() - t
        relation, stats = super().generate(weights, bias)
        self.last_fraction = stats['forward_endpoints'] / self.samples
        self.last_path = path
        self.switches += int(switched)
        return relation, dict(stats, selected_path=path, switched=switched,
                              previous_refresh_fraction=previous,
                              decision_seconds=decision_seconds)
