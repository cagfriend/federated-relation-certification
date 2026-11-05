"""Design and exactness regression tests, with small independent fixture runs."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits
from experiments.stl10_compute.design import plan as old_plan
from experiments.stl10_transfer.engine import run as old_engine
from experiments.stl10_transfer.run import seal
from experiments.noniid_clustering.data import partition_indices
from .design import plan, schedule, filename
from . import data
from .engine import run
from .run import verify_record, verify_groups, non_time_rows


class DesignTests(unittest.TestCase):
    def test_matrix_and_budgets(self):
        for regime in ('fixed_total', 'fixed_per_client'):
            jobs = schedule('full', regime)
            self.assertEqual(len(jobs), 54)
            self.assertEqual(len({filename(j) for j in jobs}), 54)
            self.assertEqual(len(schedule('full', regime, memory=True)), 12)
            self.assertEqual({m: sum(j['method'] == m and j['position'] == 0 for j in jobs) for m in ('B', 'E', 'D')}, {'B': 6, 'E': 6, 'D': 6})
            for s in plan('full', regime):
                c = s.config
                n = len(c.dimensions)
                self.assertEqual(c.train_limit - c.public_pool, 5000 if regime == 'fixed_total' else n * 400)
                self.assertEqual((c.classes, c.samples, c.degree, s.steps, s.private_limit), (10, 16384, 1, 2, None))
                self.assertEqual(c.dimensions.count(512), n // 2)
                self.assertEqual(c.dimensions.count(2048), n // 2)
        self.assertEqual(plan('full', 'fixed_total')[1].json(), old_plan('full')[0].json())
        self.assertEqual(len(schedule('full', 'all')), 108)

    def test_partitions_disjoint_and_exact_capacity(self):
        # Real-formal sizes but no AE or training: independently exercise all N partitions.
        labels = np.arange(5000) % 10
        for regime in ('fixed_total', 'fixed_per_client'):
            for s in plan('full', regime):
                total = s.config.train_limit - s.config.public_pool
                n = len(s.config.dimensions)
                for part in ('iid', 'dirichlet_0.1'):
                    _, ids, _ = partition_indices(labels[:total], 0, n, 1001, part)
                    np.testing.assert_array_equal(np.sort(np.concatenate(ids)), np.arange(total))
                    self.assertEqual([len(v) for v in ids], [len(v) for v in np.array_split(np.arange(total), n)])

    def test_corrupt_historical_marker_is_not_silently_reprepared(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p / 'prepared_iid_seed_1001.json').write_text(json.dumps(dict(path=str(p / 'missing'), metadata_sha256='bad')))
            with self.assertRaisesRegex(ValueError, 'digest mismatch'):
                data._source_reusable(old_plan('full')[0].config, 1001, 'iid', False, p)


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        spec = plan('smoke', 'fixed_total')[0]
        cls.spec = replace(spec, config=replace(spec.config, rounds=2))
        cls.prepared = data.prepare(cls.root / 'cache', cls.root / 'raw', cls.spec, 1001, 'iid', fixture=True)
        cls.runs = []
        with threadpool_limits(limits=1):
            for method in ('B', 'E', 'D'):
                meta = dict(seed=1001, partition='iid', regime='fixed_total', clients=2, method=method)
                record = run(cls.prepared, cls.spec, method, fixture=True)
                record.update(meta, memory_mode=False, process_peak_bytes=0)
                cls.runs.append((meta, seal(record)))
            cls.old = old_engine(cls.prepared, cls.spec, 'B', fixture=True)
            cls.memory = run(cls.prepared, cls.spec, 'D', fixture=True, memory=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_unchanged_engine_and_all_methods(self):
        for m, r in self.runs:
            verify_record(r, m, self.spec, self.prepared, False, True)
        verify_groups(self.runs)
        self.assertEqual(non_time_rows(self.runs[0][1]), non_time_rows(self.old))
        self.assertEqual(self.runs[0][1]['metrics'], self.old['metrics'])
        self.assertEqual(non_time_rows(self.memory), non_time_rows(self.runs[2][1]))

    def test_resealed_wrong_workload_rejected(self):
        m, r = self.runs[0]
        bad = copy.deepcopy(r)
        bad['round_records'][0]['public_optimizer_steps'] += 1
        with self.assertRaisesRegex(ValueError, 'Public step'):
            verify_record(seal(bad), m, self.spec, self.prepared, False, True)

    def test_resealed_wrong_trajectory_rejected(self):
        altered = copy.deepcopy(self.runs)
        altered[2][1]['round_records'][0]['committed_counts_digest'] = 'wrong'
        with self.assertRaisesRegex(ValueError, 'Trajectory mismatch'):
            verify_groups(altered)

    def test_memory_validation(self):
        meta = self.runs[2][0]
        record = copy.deepcopy(self.memory)
        record.update(meta, memory_mode=True, process_peak_bytes=0)
        verify_record(seal(record), meta, self.spec, self.prepared, True, True)
        record['validation']['relation_comparisons'] = 1
        with self.assertRaisesRegex(ValueError, 'Memory run contains'):
            verify_record(seal(record), meta, self.spec, self.prepared, True, True)


if __name__ == '__main__':
    unittest.main()
