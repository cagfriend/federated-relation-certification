"""Replay the production generators and time their existing phase boundaries."""

from functools import partial
from time import perf_counter

import numpy as np

from experiments.public_scaling.endpoint_bias import EndpointBiasGenerator
from experiments.snapshot_certification_timing.worker import battery, suspend_clock

from ..bias_resources.worker import generate, load_trace
from ..numerical_boundary.guard import GuardedGenerator

METHODS = ('D', 'W', 'S', 'C')
GUARDS = {'W': (True, False), 'S': (False, True), 'C': (True, True)}
PHASES = ('advance', 'candidate', 'scale', 'refresh', 'dense')


class PhaseTimers:
    def __init__(self, *args, **kwargs):
        self.times = {key: 0. for key in PHASES}
        super().__init__(*args, **kwargs)

    def _advance(self, weights, bias):
        start = perf_counter()
        super()._advance(weights, bias)
        self.times['advance'] += perf_counter()-start

    def candidate_sets(self):
        start = perf_counter()
        result = super().candidate_sets()
        self.times['candidate'] += perf_counter()-start
        return result

    def _refresh(self, ids, weights, bias):
        start = perf_counter()
        super()._refresh(ids, weights, bias)
        self.times['refresh'] += perf_counter()-start


class ProfiledD(PhaseTimers, EndpointBiasGenerator):
    pass


class ProfiledGuard(PhaseTimers, GuardedGenerator):
    def risky(self, weights, bias):
        if self.round == 0:
            return super().risky(weights, bias)
        start = perf_counter()
        result = super().risky(weights, bias)
        self.times['scale'] += perf_counter()-start
        return result

    def generate(self, weights, bias):
        scale, advance = self.times['scale'], self.times['advance']
        start = perf_counter()
        result = super().generate(weights, bias)
        elapsed = perf_counter()-start
        if self.fallback:
            self.times['dense'] += elapsed - (self.times['scale']-scale) - (self.times['advance']-advance)
        return result


def factory_for(method, profile):
    if method == 'D':
        return ProfiledD if profile else EndpointBiasGenerator
    interval, dense = GUARDS[method]
    cls = ProfiledGuard if profile else GuardedGenerator
    return partial(cls, interval=interval, dense=dense)


def replay(path, cfg, rounds, method, profile):
    edges, packed, arrays = load_trace(path, cfg)
    warm = np.ones((32, 32))
    _ = warm @ warm
    instances = []
    construct = factory_for(method, profile)

    def factory(x, w, b, graph):
        generator = construct(x, w, b, graph)
        instances.append(generator)
        return generator

    power_start, suspend_start = battery(), suspend_clock()
    result = generate(factory, arrays, edges, packed[:rounds], cfg)
    power_end, suspend_end = battery(), suspend_clock()
    result.update(
        power=[power_start, power_end],
        suspend_seconds=None if None in (suspend_start, suspend_end) else max(0., suspend_end-suspend_start),
        scale_fallbacks=sum(getattr(g, 'scale_rounds', 0) for g in instances),
        rebuilds=sum(getattr(g, 'rebuild_rounds', 0) for g in instances),
    )
    if profile:
        phases = {key: sum(g.times[key] for g in instances) for key in PHASES}
        init = result['rows'][0]['seconds']
        other = sum(row['seconds'] for row in result['rows'][1:]) - sum(phases.values())
        result['phases'] = dict(initialization=init, **phases, other=other)
    return result


def eligible(result):
    return (result['power'] == [True, True] and result['suspend_seconds'] is not None
            and result['suspend_seconds'] < 1.)
