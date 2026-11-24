"""Ensure instrumentation preserves both generation output and the continuous cache."""

import unittest

import numpy as np

from experiments.public_scaling.certification import make_matching
from experiments.public_scaling.generation import make_generator
from .phases import factory


class PhaseTests(unittest.TestCase):
    def test_profiled_paths_match_original(self):
        rng = np.random.default_rng(7)
        features = rng.normal(size=(32, 8))
        weights, bias = rng.normal(size=(4, 8)), rng.normal(size=4)
        graph = make_matching(len(features), seed=9)
        for mode in ('full', 'relation'):
            with self.subTest(mode=mode):
                args = (features, weights, bias, graph, mode)
                rows = []
                reference, profiled = make_generator(*args), factory(rows, 1)(*args)
                np.testing.assert_array_equal(reference.initial_relations, profiled.initial_relations)
                endpoints = []
                for factor in (0., .01, .2, 1.):
                    w = weights + factor*rng.normal(size=weights.shape)
                    b = bias + factor*rng.normal(size=bias.shape)
                    expected, expected_stats = reference.generate(w, b)
                    actual, actual_stats = profiled.generate(w, b)
                    np.testing.assert_array_equal(expected, actual)
                    self.assertEqual(expected_stats, actual_stats)
                    for key in reference.persistent_arrays():
                        np.testing.assert_array_equal(getattr(reference, key), getattr(profiled, key))
                    endpoints.append(actual_stats['forward_endpoints'])
                self.assertEqual([r['round'] for r in rows], [1, 2, 3, 4, 5])
                self.assertEqual([r['forward_endpoints'] for r in rows], [len(features), *endpoints])
                self.assertTrue(all(row.keys() == rows[0].keys() for row in rows))
                if mode == 'relation':
                    self.assertIn(0, endpoints)
                    self.assertGreater(sum(r['feature_gather'] for r in rows), 0.)
