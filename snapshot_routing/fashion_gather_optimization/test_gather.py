"""Regression tests for selection semantics and continuous generator state."""

from collections import Counter
import unittest

import numpy as np

from experiments.public_scaling.certification import make_matching
from experiments.public_scaling.generation import make_generator
from .gather import ALLOCATE, BASE, REUSE, Collector, GatherGenerator, cache_digest
from .run import HELD_OUT, PARTITIONS, blocks_for, cases_for
from .screening import select


class GatherTests(unittest.TestCase):
    def test_buffer_reused_across_widths_and_endpoint_counts(self):
        collector = Collector(REUSE, 32, (8, 16))
        for width, count in ((8, 0), (8, 10), (16, 32), (16, 1), (8, 32)):
            x = np.arange(32*width, dtype=np.float64).reshape(32, width)
            ids = np.arange(count, dtype=np.intp)
            rows = collector.get(x, ids)
            np.testing.assert_array_equal(rows, x[ids])
            self.assertTrue(rows.flags.c_contiguous)
            self.assertEqual(collector.nbytes, 32*16*8)

    def test_refresh_preserves_edges_and_cache(self):
        rng = np.random.default_rng(1101)
        features = rng.normal(size=(32, 8))
        initial = rng.normal(size=(4, 8))
        bias = rng.normal(size=4)
        graph = make_matching(32, 211)
        for method in (ALLOCATE, REUSE):
            with self.subTest(method=method):
                collector = Collector(method, 32, (8,))
                optimized = GatherGenerator(features, initial, bias, graph, collector.get)
                ref = make_generator(features, initial, bias, graph, 'relation')
                for scale in (0., .03, .1, 1., .001):
                    w = initial + scale*rng.normal(size=initial.shape)
                    b = bias + scale*rng.normal(size=bias.shape)
                    edges, stats = ref.generate(w, b)
                    new_edges, new_stats = optimized.generate(w, b)
                    self.assertEqual(stats, new_stats)
                    np.testing.assert_array_equal(edges, new_edges)
                    self.assertEqual(cache_digest(ref), cache_digest(optimized))

    def test_screening_stops_when_collectors_miss_threshold(self):
        def case(allocate, reuse):
            runs = {method: {'seconds': seconds}
                    for method, seconds in ((BASE, 100), (ALLOCATE, allocate), (REUSE, reuse))}
            return {'blocks': [dict(eligible=True, runs=runs)]*6}

        cells = {'1': case(95, 86), '2': case(97, 94), '3': case(96, 96)}
        self.assertEqual(select(cells, 'full')[:2], ('screen_failed', None))
        cells['3'] = case(96, 88)
        self.assertEqual(select(cells, 'full')[:2], ('screen_passed', REUSE))

    def test_held_out_blocks_balance_every_order(self):
        cases = cases_for(HELD_OUT, PARTITIONS, 'full')
        counts = Counter((cell, order) for cell, _, order in blocks_for(cases, 'full'))
        self.assertEqual(len(counts), 36)
        self.assertEqual(set(counts.values()), {1})
