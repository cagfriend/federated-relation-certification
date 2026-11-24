"""Feature-row collection variants and isolated instrumentation for E55."""

import ast
import hashlib

import numpy as np

from experiments.public_scaling.endpoint_bias import EndpointBiasGenerator
from experiments.snapshot_certification_timing.design import require
from ..fashion_confirmation import worker as fashion
from ..fashion_generation_profile.phases import timed_method

BASE = 'D'
ALLOCATE = 'take_allocate'
REUSE = 'take_reuse'
METHODS = (BASE, ALLOCATE, REUSE)


def replace_row_selection(body):
    score, = [node for node in body if ast.unparse(node).startswith('scores = ')]
    if ast.unparse(score) != 'scores = self.features[ids] @ weights.T + bias':
        raise RuntimeError('Refresh scoring expression changed')
    score.value.left.left = ast.parse('self.collect(self.features, ids)', mode='eval').body
    return body


class GatherGenerator(EndpointBiasGenerator):
    """Use the same refresh statements with only feature selection replaced."""

    _refresh = timed_method('_refresh', replace_row_selection)

    def __init__(self, features, weights, bias, edges, collect):
        self.collect = collect
        super().__init__(features, weights, bias, edges)


class Collector:
    def __init__(self, method, samples, dimensions):
        require(method in METHODS, 'Unknown collection method')
        self.method = method
        self.capacity = samples * max(dimensions)
        self.buffer = None

    def get(self, features, ids):
        if self.method == BASE:
            return features[ids]
        if self.method == ALLOCATE:
            return np.take(features, ids, axis=0, mode='clip')
        if self.buffer is None:
            self.buffer = np.empty(self.capacity, dtype=np.float64)
        # The engine consumes this view synchronously before the next refresh.
        rows, width = len(ids), features.shape[1]
        view = self.buffer[:rows*width].reshape(rows, width)
        return np.take(features, ids, axis=0, out=view, mode='clip')

    @property
    def nbytes(self):
        return 0 if self.buffer is None else self.buffer.nbytes


def cache_digest(generator):
    digest = hashlib.sha256()
    for key in sorted(generator.persistent_arrays()):
        digest.update(key.encode('utf-8'))
        digest.update(getattr(generator, key).tobytes())
    return digest.hexdigest()


def generator_factory(method, collector, *, on_refresh=None, cache_rows=None):
    """Keep request and cache observers out of the performance runs."""
    clients = 0

    def construct(features, weights, bias, edges, mode):
        nonlocal clients
        client = clients
        clients += 1
        if method in (ALLOCATE, REUSE):
            require(mode == 'relation', 'Optimized collection requires D')
            gen = GatherGenerator(features, weights, bias, edges, collector.get)
        else:
            gen = fashion_default(features, weights, bias, edges, mode)
        if on_refresh is not None:
            refresh = gen._refresh

            def record(ids, w, b):
                require(ids.ndim == 1, 'Refresh endpoints must be a vector')
                if len(ids):
                    require(ids[0] >= 0 and ids[-1] < gen.samples and np.all(ids[1:] > ids[:-1]),
                            'Refresh requires sorted unique in-range endpoints')
                on_refresh(gen.round+1, client, gen.features, ids, w, b)
                return refresh(ids, w, b)

            gen._refresh = record
        if cache_rows is not None:
            cache_rows.append(dict(round=1, client=client, digest=cache_digest(gen)))
            generate = gen.generate

            def collect_state(w, b):
                result = generate(w, b)
                cache_rows.append(dict(round=gen.round+1, client=client, digest=cache_digest(gen)))
                return result

            gen.generate = collect_state
        return gen

    return construct


# Capture the standard factory before the experiment temporarily replaces it.
fashion_default = fashion.generator
