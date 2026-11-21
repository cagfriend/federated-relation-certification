"""Current teacher generation entry point for frozen-feature training."""
from .certification import RelationGenerator as ReferenceGenerator
from .endpoint_bias import EndpointBiasGenerator


def make_generator(features, weights, bias, edges, mode, *, exact_integer=False):
    """Select endpoint bias for the float relation method and retain the B/E references."""
    if mode == "relation" and not exact_integer:
        return EndpointBiasGenerator(features, weights, bias, edges)
    return ReferenceGenerator(features, weights, bias, edges, mode, exact_integer=exact_integer)
