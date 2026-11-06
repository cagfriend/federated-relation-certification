"""Regression checks for the intervention and historical-reference adapters."""
import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from threadpoolctl import threadpool_limits
from experiments.client_scaling.design import plan
from experiments.public_scaling.data import Prepared
from experiments.public_scaling.engine import heads_digest
from experiments.private_workload import engine as original
from experiments.stl10_transfer import data as transfer
from experiments.stl10_transfer.engine import run as old_run
from experiments.stl10_transfer.run import seal
from .engine import drive
from .run import branch_spec, validate, check_reference, checkpoints
from .report import reports


class InterventionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scratch = Path(__file__).resolve().parent / 'test_artifacts'
        cls.scratch.mkdir(exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(dir=cls.scratch)
        root = Path(cls.tmp.name)
        spec = plan('smoke', 'fixed_total')[-1]
        cls.base = replace(spec, config=replace(spec.config, rounds=3))
        cls.path = transfer.prepare(root / 'cache', root / 'raw', cls.base.config, 1001, 'dirichlet_0.1', fixture=True)
        cls.results = {}
        with threadpool_limits(limits=1):
            cls.anchor = old_run(cls.path, cls.base, 'B', fixture=True)
            for arm in ('private_only', 'public1', 'public2_half', 'reference2'):
                data = Prepared(cls.path, cls.base.config, allow_test_fixture=True)
                try:
                    cls.results[arm] = seal(drive(data, cls.base, arm))
                finally:
                    data.close()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_interventions_and_reference(self):
        check_reference(self.results['reference2'], self.anchor)
        for arm, result in self.results.items():
            validate(result, self.base, self.anchor)
        self.assertEqual(branch_spec(self.base, 'public2_half').config.head_lr, self.base.config.head_lr)
        self.assertEqual(branch_spec(self.base, 'public2_half').config.public_weight, .5)
        self.assertIn(180, checkpoints(200))

    def test_reduced_arms_match_original_student(self):
        with threadpool_limits(limits=1):
            for arm in ('public1', 'public2_half'):
                expected = old_run(self.path, branch_spec(self.base, arm), 'B', fixture=True)
                check_reference(self.results[arm], expected)

    def test_private_only_matches_pure_private_updates(self):
        with threadpool_limits(limits=1):
            data = Prepared(self.path, self.base.config, allow_test_fixture=True)
            try:
                method = original.WorkloadMethod('B', data, self.base)
                for rnd in range(1, 4):
                    for client, head in enumerate(method.heads):
                        original.private_workload_epoch(head, data.private[client], data.pseudo[client], self.base.config,
                                                        data.seed, client, rnd, None)
                    self.assertEqual(heads_digest(method.heads), self.results['private_only']['round_records'][rnd-1]['head_digest_after_public'])
            finally:
                data.close()

    def test_observers_do_not_change_training(self):
        with threadpool_limits(limits=1):
            data = Prepared(self.path, self.base.config, allow_test_fixture=True)
            try:
                result = drive(data, self.base, 'reference2', observations=False)
            finally:
                data.close()
        check_reference(result, self.anchor)
        self.assertEqual(result['metrics'], [])

    def test_exception_restores_callbacks(self):
        private, public = original.private_workload_epoch, original.update
        data = Prepared(self.path, self.base.config, allow_test_fixture=True)
        try:
            with patch.object(original, 'update', side_effect=RuntimeError('injected')) as injected:
                with self.assertRaisesRegex(RuntimeError, 'injected'):
                    drive(data, self.base, 'public1', observations=False)
                self.assertIs(original.update, injected)
            self.assertIs(original.private_workload_epoch, private)
            self.assertIs(original.update, public)
        finally:
            data.close()

    def test_resealed_bad_workload_rejected(self):
        record = copy.deepcopy(self.results['private_only'])
        record['round_records'][0]['public_optimizer_steps'] = 1
        with self.assertRaisesRegex(ValueError, 'Actual public workload'):
            validate(seal(record), self.base, self.anchor)

    def test_valid_other_arm_cannot_replace_a_resume_file(self):
        record = dict(self.results['public1'], seed=1001, partition='dirichlet_0.1')
        anchor = dict(self.anchor, partition='dirichlet_0.1')
        with self.assertRaisesRegex(ValueError, 'Arm or source identity'):
            validate(seal(record), self.base, anchor, expected_arm='public2_half')

    def test_report_and_checkpoint_schedule(self):
        with tempfile.TemporaryDirectory(dir=self.scratch) as tmp:
            reports(Path(tmp), {a: self.results[a] for a in ('private_only', 'public1', 'public2_half')}, self.anchor)
            self.assertIn('historical_public2', (Path(tmp)/'report.md').read_text(encoding='utf-8'))
        self.assertEqual(checkpoints(200), [0,1,2,5,10,20,40,60,80,100,120,140,160,180,200])


if __name__ == '__main__':
    unittest.main()
