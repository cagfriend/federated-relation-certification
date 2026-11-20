"""Run one exact relation path on an immutable sequence of teacher heads."""

from collections import Counter
from time import perf_counter

import numpy as np

from experiments.public_scaling.certification import RelationGenerator
from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_certification_timing.engine import MODES
from experiments.snapshot_certification_timing.worker import battery, peak_bytes, suspend_clock

METHODS = ('B', 'E', 'D', 'S', 'C')
POLICY = dict(window=8, memory_per_client=8 * 1024**2, close_ratio=1.10,
              margin=0.05, noise_multiplier=2.0, min_future=32)


def cache_estimate(method, features, bias):
    if method == 'B':
        return 0
    samples, width = features.shape
    classes = len(bias)
    # Float64 prefixes, reference budgets, gaps, radius, last head; int/uint64 IDs and bit powers.
    return 8 * (3*samples*classes + 3*samples + 2*classes**2 + classes*width + 2*classes)


class ClientPath:
    def __init__(self, method, rule, features, bias, edges, horizon, smoke):
        self.features, self.edges = features, edges
        self.generators = {}
        self.route = rule['first'] if method in ('S', 'C') else method
        self.start_route = self.route
        self.trial = rule['second'] if method == 'C' else None
        self.primary_times, self.trial_times = [], []
        self.probe_seconds = 0.
        self.window = min(POLICY['window'], horizon)
        self.reason = 'fixed' if method in ('B', 'E', 'D', 'S') else 'clear_static_choice'
        if method in ('S', 'C') and cache_estimate(self.route, features, bias) > POLICY['memory_per_client']:
            self.route = self.start_route = 'B'
            self.trial, self.reason = None, 'memory'
        if self.trial is not None:
            total = sum(cache_estimate(m, features, bias) for m in (self.route, self.trial))
            if total > POLICY['memory_per_client']:
                self.trial, self.reason = None, 'memory'
            elif not smoke and horizon-self.window < POLICY['min_future']:
                self.trial, self.reason = None, 'short_horizon'
            elif not smoke and battery() is not True:
                self.trial, self.reason = None, 'power'
            elif not smoke and (horizon-self.window)*rule['possible_gain'] <= self.window*rule['trial_cost']:
                self.trial, self.reason = None, 'probe_cost'
            else:
                self.reason = 'calibrating'
        self.smoke, self.horizon = smoke, horizon
        self.peak_cache = 0

    def generate(self, method, w, b, rnd):
        if rnd == 0:
            g = RelationGenerator(self.features, w, b, self.edges, MODES[method])
            self.generators[method] = g
            relation = g.initial_relations
            del g.initial_relations
            return relation, len(self.features)
        rel, stat = self.generators[method].generate(w, b)
        return rel, stat['forward_endpoints']

    def step(self, w, b, rnd):
        if self.trial is None:
            rel, touched = self.generate(self.route, w, b, rnd)
            if rnd == 0:
                self.peak_cache = self.cache_bytes()
            return rel, touched, None, str(self.route)

        # Alternate order to avoid always granting one path the warmer arrays.
        costs, output = {}, {}
        paths = (self.route, self.trial)
        for method in paths if rnd % 2 == 0 else paths[::-1]:
            start = perf_counter()
            output[method] = self.generate(method, w, b, rnd)
            costs[method] = perf_counter() - start
        self.probe_seconds += costs[self.trial]
        rel, touched = output[self.route]
        probe = output[self.trial][0]
        executed = str(self.route)
        if rnd == 0:
            self.peak_cache = self.cache_bytes()
            require(self.peak_cache <= POLICY['memory_per_client'], 'Calibration cache exceeds its budget')
        else:
            # Pay for initialization, but estimate steady time from subsequent rounds.
            self.primary_times.append(costs[self.route])
            self.trial_times.append(costs[self.trial])
        if rnd + 1 == self.window:
            self.finish(rnd)
        return rel, touched, probe, executed

    def finish(self, rnd):
        future = self.horizon-rnd-1
        self.reason = 'insufficient_savings'
        if not self.smoke and battery() is not True:
            self.reason = 'power'
        elif self.primary_times:
            primary = np.asarray(self.primary_times)
            delta = primary-np.asarray(self.trial_times)
            center = float(np.median(delta))
            deviation = float(np.median(np.abs(delta-center)))
            net_per_round = center - max(POLICY['margin'] * float(np.median(primary)),
                                         POLICY['noise_multiplier'] * deviation)
            if future * net_per_round > self.probe_seconds:
                self.route, self.trial = self.trial, self.route
                self.reason = 'switched'
        del self.generators[self.trial]
        self.trial = None

    def cache_bytes(self):
        return sum(sum(g.persistent_arrays().values()) for g in self.generators.values())


def replay(method, trace, rules, smoke):
    edges = trace['edges']
    exact = trace['relations']
    weights, biases, features = [
        [trace[f'{prefix}{i}'] for i in range(exact.shape[1])]
        for prefix in ('w', 'b', 'x')
    ]
    rounds, clients = exact.shape[:2]
    power = Counter()

    def power_check():
        state = battery()
        power['unknown' if state is None else ('ac' if state else 'battery')] += 1

    power_check()
    sleep_start = suspend_clock()
    input_peak = peak_bytes()
    start = perf_counter()
    paths = [ClientPath(method, rules[str(x.shape[1])] if method in ('S', 'C') else {},
                        x, b[0], edges, rounds, smoke) for x, b in zip(features, biases)]
    setup = perf_counter()-start
    rows, comparisons, probe_checks = [], 0, 0
    cache_peak = 0
    for rnd in range(rounds):
        peers, details = [], []
        begin = perf_counter()
        for c, path in enumerate(paths):
            start = perf_counter()
            item = path.step(weights[c][rnd], biases[c][rnd], rnd)
            elapsed = perf_counter()-start
            peers.append(item)
            details.append(elapsed)
        rounded_seconds = perf_counter()-begin
        # All verification and operating-system sampling sit outside the measured stage.
        for c, (relation, _, probe, _) in enumerate(peers):
            expected = np.unpackbits(exact[rnd, c], count=len(edges))
            require(np.array_equal(relation, expected), f'{method}: wrong relation at {rnd+1}, client {c}')
            comparisons += len(edges)
            if probe is not None:
                require(np.array_equal(probe, expected), f'C probe: wrong relation at {rnd+1}, client {c}')
                probe_checks += len(edges)
        if rnd == 0:
            cache_peak = sum(p.peak_cache for p in paths)
        rows.append(dict(seconds=rounded_seconds, clients=details, routes=[r for _, _, _, r in peers],
                         endpoints=[n for _, n, _, _ in peers]))
        if (rnd+1) % 10 == 0 or rnd+1 == rounds:
            power_check()
    sleep_end = suspend_clock()
    return dict(rows=rows, setup_seconds=setup, comparisons=comparisons, probe_comparisons=probe_checks,
                power=dict(power), suspend_seconds=None if None in (sleep_start, sleep_end)
                else max(0., sleep_end-sleep_start), input_peak_bytes=input_peak, process_peak_bytes=peak_bytes(),
                peak_cache_bytes=cache_peak, final_cache_bytes=sum(p.cache_bytes() for p in paths),
                selections=[dict(initial=p.start_route, final=p.route, reason=p.reason,
                                 trial_seconds=p.probe_seconds) for p in paths])
