import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from experiments.public_scaling.head import Head
from experiments.stl10_diagnostics.probes import (
    feature_probe,
    fixed_public_indices,
    gradient_probe,
    initial_inspection,
    nearest_centers,
    probe,
)


class ProbeTests(unittest.TestCase):
    def test_probe_is_read_only_and_reports_pseudo_fit(self):
        head = Head(3, 2, seed=17, client=0)
        head.w[:] = [[2.0, 0.0, 0.0], [-2.0, 0.0, 0.0]]
        head.b[:] = 0.0
        before_w, before_b = head.w.copy(), head.b.copy()
        z = np.vstack((np.tile([1.0, 0.0, 0.0], (600, 1)), np.tile([-1.0, 0.0, 0.0], (7, 1))))
        pseudo = np.r_[np.zeros(600, dtype=np.int64), np.ones(7, dtype=np.int64)]
        before_z, before_pseudo = z.copy(), pseudo.copy()
        result = probe(head, z, pseudo=pseudo, indices=np.arange(3, 40))
        self.assertEqual(result["cluster_counts"], [37, 0])
        self.assertEqual(result["occupied_clusters"], 1)
        self.assertEqual(result["pseudo_accuracy"], 1.0)
        self.assertGreater(result["pseudo_ce"], 0.0)
        np.testing.assert_array_equal(head.w, before_w)
        np.testing.assert_array_equal(head.b, before_b)
        np.testing.assert_array_equal(z, before_z)
        np.testing.assert_array_equal(pseudo, before_pseudo)

    def test_probe_indices_select_all_statistics_with_or_without_pseudo(self):
        head = Head(2, 3, seed=23, client=0)
        z = np.array([[2.0, 0.0], [0.0, 2.0], [-2.0, 0.0], [0.0, -2.0],
                      [1.0, 1.0], [-1.0, -1.0]])
        pseudo = np.array([0, 1, 2, 2, 1, 0], dtype=np.int64)
        ids = np.array([1, 2, 5], dtype=np.int64)
        selected = probe(head, z[ids])
        indexed = probe(head, z, indices=ids)
        self.assertEqual(indexed, selected)
        selected_with_pseudo = probe(head, z[ids], pseudo=pseudo[ids])
        indexed_with_pseudo = probe(head, z, pseudo=pseudo, indices=ids)
        self.assertEqual(indexed_with_pseudo, selected_with_pseudo)

    def test_feature_probe_stats_and_nonfinite_rejection(self):
        z = np.array([[0.0, 0.0], [2.0, 0.0]])
        result = feature_probe(z)
        self.assertEqual(result["finite_fraction"], 1.0)
        self.assertAlmostEqual(result["centered_discrete_rms"], 1.0)
        self.assertAlmostEqual(result["mean_norm"], 1.0)
        with self.assertRaises(ValueError):
            feature_probe(np.array([[np.nan, 0.0]]))

    def test_nearest_centers_known_example_and_ties(self):
        z = np.array([[0.0, 0.0], [2.1, 2.0], [-2.0, 0.0], [0.9, 1.0]])
        centers = np.array([[0.0, 0.0], [2.0, 2.0], [-2.0, 0.0]])
        np.testing.assert_array_equal(nearest_centers(z, centers), [0, 1, 2, 0])
        # Equal-distance ties are resolved by the lowest center index.
        np.testing.assert_array_equal(nearest_centers(np.array([[1.0, 0.0]]), centers[:2]), [0])

    def test_gradient_probe_is_read_only_and_uses_local_sampling_stream(self):
        head = Head(4, 3, seed=9, client=1)
        before_w, before_b = head.w.copy(), head.b.copy()
        private = np.arange(80, dtype=np.float64).reshape(20, 4) / 80
        pseudo = np.arange(20, dtype=np.int64) % 3
        public = np.arange(120, dtype=np.float64).reshape(30, 4) / 120
        edges = np.array([[i, (i + 1) % 30] for i in range(25)], dtype=np.int64)
        targets = np.linspace(0.1, 0.9, len(edges))
        private_before, public_before = private.copy(), public.copy()
        pseudo_before, edges_before, targets_before = pseudo.copy(), edges.copy(), targets.copy()
        cfg = SimpleNamespace(head_lr=0.1, public_weight=0.7)
        global_before = np.random.get_state()
        one = gradient_probe(head, private, pseudo, public, edges, targets, cfg, 31, 2)
        two = gradient_probe(head, private, pseudo, public, edges, targets, cfg, 31, 2)
        global_after = np.random.get_state()
        self.assertEqual(one, two)
        self.assertEqual(one["private_sample_count"], 20)
        self.assertEqual(one["public_edge_count"], 25)
        self.assertGreaterEqual(one["private_gradient_norm"], 0)
        self.assertAlmostEqual(one["public_weighted_update_norm"], 0.07 * one["public_gradient_norm"])
        self.assertEqual(global_before[0], global_after[0])
        np.testing.assert_array_equal(global_before[1], global_after[1])
        np.testing.assert_array_equal(head.w, before_w)
        np.testing.assert_array_equal(head.b, before_b)
        np.testing.assert_array_equal(private, private_before)
        np.testing.assert_array_equal(public, public_before)
        np.testing.assert_array_equal(pseudo, pseudo_before)
        np.testing.assert_array_equal(edges, edges_before)
        np.testing.assert_array_equal(targets, targets_before)

    def test_fixed_public_indices_are_stable_and_bounded(self):
        cfg = SimpleNamespace(samples=1500)
        a = fixed_public_indices(cfg, 1001, 3)
        b = fixed_public_indices(cfg, 1001, 3)
        self.assertEqual(len(a), 1024)
        np.testing.assert_array_equal(a, b)
        self.assertTrue(np.all((a >= 0) & (a < cfg.samples)))

    def test_initial_inspection_summarizes_centers_and_head_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            centers = np.array([[-1.0, 0.0], [1.0, 0.0]])
            np.save(directory / "client_0_centers.npy", centers)
            private = np.array([[-1.1, 0.0], [-0.8, 0.0], [1.1, 0.0], [0.9, 0.0]])
            pseudo = np.array([0, 0, 1, 1])
            public = np.array([[-1.0, 0.0], [0.0, 0.0], [1.0, 0.0]])
            test = public.copy()
            data = SimpleNamespace(directory=directory, private=[private], pseudo=[pseudo], public=[public],
                                   test=[test], test_labels=np.array([0, 0, 1]))
            head = Head(2, 2, 4, 0)
            before_w, before_b = head.w.copy(), head.b.copy()
            cfg = SimpleNamespace(dimensions=(2,), classes=2)
            result = initial_inspection(data, [head], cfg)
            client = result["clients"][0]
            self.assertEqual(client["private_pseudo_histogram"], [2, 2])
            self.assertEqual(client["private_pseudo_nearest_center_mismatches"], 0)
            self.assertEqual(client["test_center_probe"]["cluster_counts"], [2, 1])
            self.assertEqual(set(client["test_center_metrics"]), {"acc", "nmi", "ari"})
            np.testing.assert_array_equal(head.w, before_w)
            np.testing.assert_array_equal(head.b, before_b)


if __name__ == "__main__":
    unittest.main()
