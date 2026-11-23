"""Use the existing head engine on prepared Fashion-MNIST features."""

import hashlib
from collections import Counter
from time import perf_counter
from unittest.mock import patch

import numpy as np

from experiments.private_prior.training import log_prior
from experiments.public_budget.student import schedule_digest
from experiments.public_scaling.certification import hard_relations, make_matching
from experiments.public_scaling.data import Prepared
from experiments.public_scaling.endpoint_bias import EndpointBiasGenerator
from experiments.public_scaling.engine import evaluate
from experiments.public_scaling.generation import make_generator
from experiments.public_scaling.head import Head
from experiments.public_scaling.protocol import RelationProtocol
from experiments.snapshot_certification_timing import engine
from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_certification_timing.worker import battery, peak_bytes, suspend_clock
from .design import GUARD, PUBLIC_STEPS, PUBLIC_WEIGHTS


def digest(array):
    return hashlib.sha256(array.tobytes()).hexdigest()


class FashionEngine(engine.Engine):
    def __init__(self, data, cfg, method):
        # The dataset preparer already fit the KMeans pseudo-labels and centers.
        # Reuse the STL-10 round/private-update methods starting at that boundary.
        self.cfg = dict(classes=cfg.classes, public_weights=PUBLIC_WEIGHTS, public_steps=PUBLIC_STEPS)
        self.config, self.mode = cfg, engine.MODES[method]
        self.private = [np.array(x, dtype=np.float64) for x in data.private]
        self.public, self.pseudo = data.public, data.pseudo
        self.heads = []
        for c, width in enumerate(cfg.dimensions):
            centers = np.load(data.directory/f'client_{c}_centers.npy', allow_pickle=False).astype(np.float64)
            require(centers.shape == (cfg.classes, width), f'Invalid KMeans centers for client {c}')
            head = Head(width, cfg.classes, data.seed, c)
            head.w = 2*centers
            head.b = -np.sum(centers**2, axis=1)
            self.heads.append(head)
        self.counts = [np.bincount(y, minlength=cfg.classes) for y in self.pseudo]
        self.all_clients = True
        self.all_log_priors = [log_prior(y, cfg.classes) for y in self.pseudo]
        self.edges = make_matching(cfg.samples, data.seed)
        self.protocol = RelationProtocol(self.edges, cfg.samples, cfg.classes, cfg.dimensions, adaptive=True)
        self.strength, self.until = GUARD, cfg.rounds
        self.generators = []


def generator(features, weights, bias, edges, mode):
    if mode == 'point':
        return EndpointBiasGenerator(features, weights, bias, edges, mode=mode)
    return make_generator(features, weights, bias, edges, mode)


def check_round(algo, stat, cfg, seed, rnd):
    for client, (x, (w, b), actual) in enumerate(zip(algo.public, algo.last_snapshot, algo.last_relations, strict=True)):
        exact = hard_relations((x@w.T+b).argmax(1), algo.edges)
        require(np.array_equal(exact, actual) and np.array_equal(exact, algo.protocol.server_relations[client]),
                f'Round {rnd}, client {client}: teacher or decoded edge differs from all-sample oracle')
    counts = np.sum(algo.last_relations, axis=0)
    require(np.array_equal(counts, algo.protocol.counts), f'Round {rnd}: counts differ')
    for client, (order, target) in enumerate(zip(stat['public_orders'], stat['consumed'], strict=True)):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 402, client, rnd, 0]))
        expected = rng.permutation(len(algo.edges))[:PUBLIC_STEPS*cfg.public_edge_batch]
        require(np.array_equal(expected, order) and np.array_equal(target, counts/len(algo.heads)),
                f'Round {rnd}, client {client}: student order or received target differs')
    return len(algo.edges)*len(algo.heads)


def evidence(algo, stat):
    orders = stat['public_orders']
    return dict(head=algo.state_digest(), traffic=algo.traffic(),
                teacher=[digest(w) + digest(b) for w, b in algo.last_snapshot],
                relations=[digest(r) for r in algo.last_relations], counts=digest(algo.protocol.counts),
                orders=schedule_digest(orders),
                targets=[digest(t[o]) for t, o in zip(stat['consumed'], orders, strict=True)],
                private_losses=stat['private_losses'], public_losses=stat['public_losses'])


def run(directory, cfg, method, *, audit):
    start = perf_counter()
    data = Prepared(directory, cfg)
    load_seconds = perf_counter()-start
    power = Counter()

    def sample_power():
        ac = battery()
        power['unknown' if ac is None else 'ac' if ac else 'battery'] += 1

    try:
        scratch = np.ones((32, 32))
        _ = scratch@scratch
        input_peak = peak_bytes()
        if not audit:
            sample_power()
        sleep_start = suspend_clock()
        start = perf_counter()
        algo = FashionEngine(data, cfg, method)
        setup = perf_counter()-start
        initial = dict(head=algo.state_digest(), graph=digest(algo.edges), public_ids=digest(data.public_ids),
                       traffic=algo.traffic())
        timing, observed, quality = [], [], []
        if audit:
            quality.append(dict(round=0, **evaluate(algo.heads, data, cfg)))
        comparisons = 0
        endpoints = np.zeros(len(cfg.dimensions), dtype=np.int64)
        stages = ('private_seconds', 'generation_seconds', 'exchange_seconds', 'public_seconds')
        with patch.object(engine, 'make_generator', generator):
            for rnd in range(1, cfg.rounds+1):
                start = perf_counter()
                stat = algo.round(None, data.public[0], data.seed, rnd)
                elapsed = perf_counter()-start
                endpoints += stat['endpoints']
                observed.append(evidence(algo, stat))
                tick = rnd % cfg.eval_every == 0 or rnd == cfg.rounds
                if audit:
                    comparisons += check_round(algo, stat, cfg, data.seed, rnd)
                    if tick:
                        quality.append(dict(round=rnd, **evaluate(algo.heads, data, cfg)))
                else:
                    timing.append(dict(round=rnd, seconds=elapsed, **{k: stat[k] for k in stages}))
                    if tick:
                        sample_power()
        sleep_end = suspend_clock()
        return dict(initial=initial, observed=observed, timing=timing, evaluations=quality, comparisons=comparisons,
                    client_endpoints=endpoints.tolist(), setup_seconds=setup, load_seconds=load_seconds,
                    preparation_seconds=data.metadata['preparation_wall_seconds_excluding_download'],
                    traffic=algo.traffic(), cache_bytes=algo.cache_bytes(),
                    protocol_bytes=algo.protocol.persistent_bytes(), input_peak_bytes=input_peak,
                    process_peak_bytes=peak_bytes(), power=dict(power),
                    suspend_seconds=None if None in (sleep_start, sleep_end) else max(0., sleep_end-sleep_start))
    finally:
        data.close()
