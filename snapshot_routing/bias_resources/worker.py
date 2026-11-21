"""Replay one D variant and profile its phases in a separate pass."""

import hashlib
from time import perf_counter

import numpy as np

from experiments.public_scaling.certification import RelationGenerator
from experiments.public_scaling.protocol import RelationProtocol
from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_certification_timing.worker import battery, peak_bytes, suspend_clock
from ..bias_numerical.candidate import EndpointBiasGenerator


def old_generator(x, w, b, edges):
    return RelationGenerator(x, w, b, edges, "relation")


class PhaseObserver:
    def reset_phases(self):
        self.advance_seconds = 0.
        self.candidates_seconds = 0.
        self.refresh_seconds = 0.

    def _advance(self, weights, bias):
        start = perf_counter()
        super()._advance(weights, bias)
        self.advance_seconds += perf_counter() - start

    def candidate_sets(self):
        start = perf_counter()
        result = super().candidate_sets()
        self.candidates_seconds += perf_counter() - start
        return result

    def _refresh(self, ids, weights, bias):
        start = perf_counter()
        super()._refresh(ids, weights, bias)
        self.refresh_seconds += perf_counter() - start


class ProfiledOld(PhaseObserver, RelationGenerator):
    def __init__(self, x, w, b, edges):
        super().__init__(x, w, b, edges, "relation")


class ProfiledNew(PhaseObserver, EndpointBiasGenerator):
    pass


METHODS = {
    "old": (old_generator, ProfiledOld),
    "new": (EndpointBiasGenerator, ProfiledNew),
}


def load_trace(path, cfg):
    rounds, samples, classes = (cfg[key] for key in ("rounds", "public_size", "classes"))
    widths = cfg["widths"]
    with np.load(path, allow_pickle=False) as trace:
        edges = trace["edges"]
        packed = trace["relations"]
        require(edges.dtype == np.uint32 and edges.shape == (samples // 2, 2)
                and np.array_equal(np.sort(edges.ravel()), np.arange(samples)),
                "Unexpected matching graph")
        require(packed.dtype == np.uint8 and packed.shape == (rounds, len(widths), (len(edges) + 7) // 8),
                "Unexpected full B relation vectors")
        arrays = [tuple(trace[f"{prefix}{c}"] for prefix in ("x", "w", "b")) for c in range(len(widths))]
    for (x, w, b), width in zip(arrays, widths, strict=True):
        require((x.shape, w.shape, b.shape) == ((samples, width), (rounds, classes, width), (rounds, classes))
                and all(a.dtype == np.float64 and np.isfinite(a).all() for a in (x, w, b)),
                "Unexpected trace dimensions, dtype or numeric values")
    return edges, packed, arrays


def generate(factory, arrays, edges, packed_b, cfg, *, profile=False):
    widths = cfg["widths"]
    fingerprint = hashlib.sha256()
    rows, generators = [], []
    first_mismatch = None
    if profile:
        protocol = RelationProtocol(edges, cfg["public_size"], cfg["classes"], tuple(widths), adaptive=True)
    for rnd, ref in enumerate(packed_b):
        vectors, points = [], []
        if profile and rnd:
            for generator in generators:
                generator.reset_phases()
        start = perf_counter()
        for client, (x, w, b) in enumerate(arrays):
            if rnd == 0:
                generator = factory(x, w[0], b[0], edges)
                generators.append(generator)
                vector = generator.initial_relations
                del generator.initial_relations
                forward = len(x)
            else:
                vector, stats = generators[client].generate(w[rnd], b[rnd])
                forward = stats["forward_endpoints"]
            vectors.append(vector)
            points.append(forward)
        elapsed = perf_counter() - start
        mismatches = []
        for client, (vector, reference) in enumerate(zip(vectors, ref, strict=True)):
            expected = np.unpackbits(reference, count=len(edges))
            different = vector != expected
            count = int(np.count_nonzero(different))
            mismatches.append(count)
            if count and first_mismatch is None:
                first_mismatch = dict(round=rnd + 1, client=client, edge_ids=np.flatnonzero(different).tolist())
            fingerprint.update(vector)
        row = dict(round=rnd + 1, seconds=elapsed, endpoints=points, mismatches=mismatches,
                   scoring_macs=cfg["classes"] * sum(p * d for p, d in zip(points, widths, strict=True)))
        if profile:
            advance = sum(g.advance_seconds for g in generators) if rnd else 0.
            candidates = sum(g.candidates_seconds for g in generators) if rnd else 0.
            refresh = sum(g.refresh_seconds for g in generators) if rnd else 0.
            protocol.exchange(vectors)
            row.update(advance_seconds=advance, candidate_seconds=candidates, refresh_seconds=refresh,
                       other_seconds=elapsed - advance - candidates - refresh,
                       traffic=protocol.traffic.snapshot())
        rows.append(row)
    return dict(rows=rows, first_mismatch=first_mismatch, relation_sha256=fingerprint.hexdigest(),
                cache_bytes=sum(sum(g.persistent_arrays().values()) for g in generators),
                edge_comparisons=packed_b.shape[0] * packed_b.shape[1] * len(edges))


def non_timing(run):
    return (run["relation_sha256"], run["cache_bytes"], run["edge_comparisons"],
            [(r["endpoints"], r["mismatches"], r["scoring_macs"]) for r in run["rows"]])


def replay(path, cfg, reference_traffic, method, profile):
    edges, packed, arrays = load_trace(path, cfg)
    warm = np.ones((32, 32))
    _ = warm @ warm
    input_peak = peak_bytes()
    power_before, suspend_before = battery(), suspend_clock()
    plain_factory, profiled_factory = METHODS[method]
    result = generate(plain_factory, arrays, edges, packed, cfg)
    peak = peak_bytes()
    power_after, suspend_after = battery(), suspend_clock()
    result.update(input_peak_bytes=input_peak, process_peak_bytes=peak,
                  power=[power_before, power_after],
                  suspend_seconds=(None if None in (suspend_before, suspend_after)
                                   else max(0., suspend_after - suspend_before)))
    if profile:
        diagnostic = generate(profiled_factory, arrays, edges, packed, cfg, profile=True)
        require(non_timing(result) == non_timing(diagnostic), "Profiling changed replay output or counters")
        result["diagnostic"] = diagnostic["rows"]
        result["traffic_rounds_equal_b"] = sum(
            row["traffic"] == expected
            for row, expected in zip(diagnostic["rows"], reference_traffic, strict=True)
        )
    return result
