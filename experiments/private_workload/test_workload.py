import hashlib
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.config import Config
from experiments.public_scaling.data import Prepared
from experiments.public_scaling.engine import heads_digest
from experiments.public_scaling.test_scaling import fixture
from experiments.public_budget.design import Spec as BudgetSpec
from experiments.public_budget.engine import BudgetMethod
from .design import Spec, plan
from .sampling import subset_indices, subset_digest, STREAM
from .engine import WorkloadMethod, run
from .report import reports


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.cfg = Config(dimensions=(6, 9), public_pool=64, samples=16, classes=3, rounds=4,
            train_limit=104, test_limit=24, pretrain_epochs=1, prepare_threads=1,
            private_batch=7, public_edge_batch=4, eval_every=2)
        self.directory = fixture(Path(self.temp.name) / 'fixture', self.cfg)

    def tearDown(self):
        self.temp.cleanup()

    def test_plans_freeze_one_preparation_and_three_workloads(self):
        specs = plan('full', 'cuda')
        self.assertEqual([(s.config.samples, s.policy, s.steps, s.private_limit) for s in specs],
                         [(16384, 'fixed', 8, None), (16384, 'fixed', 8, 2048), (16384, 'fixed', 8, 1024)])
        self.assertEqual(len({str(s.config.preparation()) for s in specs}), 1)
        self.assertEqual([s.case_id for s in specs],
                         ['m16384_fixed8_privfull', 'm16384_fixed8_priv2048', 'm16384_fixed8_priv1024'])
        smoke = plan('smoke', 'cpu')
        self.assertEqual([(s.config.samples, s.steps, s.private_limit) for s in smoke],
                         [(128, 1, None), (128, 1, 128), (128, 1, 64)])
        with self.assertRaises(ValueError):
            Spec(self.cfg, 'fixed', 2, 0).validate()
        with self.assertRaises(ValueError):
            Spec(self.cfg, 'full', 2, None).validate()

    def test_subset_stream_is_deterministic_and_method_independent(self):
        a = subset_indices(7, 1, 3, 20, 9)
        b = subset_indices(7, 1, 3, 20, 9)
        np.testing.assert_array_equal(a, b)
        expected = np.random.default_rng(np.random.SeedSequence([7, STREAM, 1, 3])).permutation(20)[:9]
        np.testing.assert_array_equal(a, expected)
        self.assertEqual(len(set(a.tolist())), 9)
        np.testing.assert_array_equal(subset_indices(7, 1, 3, 20, None), np.arange(20))
        np.testing.assert_array_equal(subset_indices(7, 1, 3, 20, 25), np.arange(20))
        self.assertNotEqual(subset_digest([a]), subset_digest([subset_indices(7, 1, 4, 20, 9)]))

    def test_full_workload_matches_public_budget_engine(self):
        with threadpool_limits(limits=1):
            d = Prepared(self.directory, self.cfg, allow_test_fixture=True)
            try:
                for name in ('B', 'E', 'D'):
                    old = BudgetMethod(name, d, BudgetSpec(self.cfg, 'fixed', 2))
                    new = WorkloadMethod(name, d, Spec(self.cfg, 'fixed', 2, None))
                    for rnd in range(1, 5):
                        a, ar, *_ = old.step(rnd)
                        b, br, *_ = new.step(rnd)
                        self.assertEqual(a['head_digest_after_public'], b['head_digest_after_public'])
                        self.assertEqual(a['traffic'], b['traffic'])
                        self.assertEqual(a['private_loss'], b['private_loss'])
                        self.assertEqual(a['private_optimizer_steps'], b['private_optimizer_steps'])
                        np.testing.assert_array_equal(ar, br)
            finally:
                d.close()

    def test_limited_step_records_exact_subset_accounting(self):
        limit = 9
        with threadpool_limits(limits=1):
            d = Prepared(self.directory, self.cfg, allow_test_fixture=True)
            try:
                model = WorkloadMethod('B', d, Spec(self.cfg, 'fixed', 2, limit))
                row, *_ = model.step(1)
                counts = [len(d.private[c]) for c in range(len(self.cfg.dimensions))]
                idxs = [subset_indices(7, c, 1, counts[c], limit) for c in range(len(counts))]
                self.assertEqual(row['private_samples_per_client'], [limit, limit])
                self.assertEqual(row['private_subset_digest'], subset_digest(idxs))
                self.assertEqual(row['private_forward_endpoints'], 2 * limit * self.cfg.private_epochs)
                self.assertEqual(row['private_optimizer_steps'],
                                 2 * ((limit + self.cfg.private_batch - 1) // self.cfg.private_batch) * self.cfg.private_epochs)
                for c in range(len(counts)):
                    hist = np.bincount(d.pseudo[c][idxs[c]], minlength=self.cfg.classes).astype(int).tolist()
                    self.assertEqual(row['private_subset_pseudo_histograms'][c], hist)
            finally:
                d.close()

    def test_limited_run_oracle_and_single_method_replay(self):
        spec = Spec(self.cfg, 'fixed', 2, 9)
        with threadpool_limits(limits=1):
            r = run(self.directory, spec, fixture=True, progress=False)
        n = len(self.cfg.dimensions); e = self.cfg.samples * self.cfg.degree // 2
        self.assertEqual(r['validation']['relation_comparisons'], 3 * self.cfg.rounds * n * e)
        self.assertEqual(r['validation']['candidate_membership_comparisons'], 2 * self.cfg.rounds * n * self.cfg.samples)
        self.assertEqual(r['validation']['mismatches'], 0)
        rows = r['round_records']
        for rnd in range(1, 5):
            self.assertEqual(len({x['head_digest_after_public'] for x in rows if x['round'] == rnd}), 1)
            self.assertEqual(len({x['private_subset_digest'] for x in rows if x['round'] == rnd}), 1)
        with threadpool_limits(limits=1):
            for name in ('B', 'E', 'D'):
                one = run(self.directory, spec, names=(name,), validate=False, metrics=False, fixture=True, progress=False)
                self.assertEqual(one['summary'][name]['final_head_digest'], r['summary'][name]['final_head_digest'])
                self.assertEqual(one['summary'][name]['private_optimizer_steps'], r['summary'][name]['private_optimizer_steps'])

    def test_report_pairing_guardrail_and_workload_effects(self):
        import csv
        cfg = self.cfg
        def case(limit, accs, head):
            spec = Spec(cfg, 'fixed', 2, limit)
            summaries = {}
            for m in ('B', 'E', 'D'):
                metric = dict(method=m, round=cfg.rounds, mean=dict(acc=sum(accs) / 2, nmi=.5, ari=.5),
                              clients=[dict(client=c, width=cfg.dimensions[c], acc=a, nmi=.5, ari=.5) for c, a in enumerate(accs)])
                summaries[m] = dict(head_pipeline_seconds=head, with_shared_preparation_seconds=head + 20, initialization_seconds=.01,
                    private_seconds=4., generation_seconds=1., exchange_seconds=.1, public_seconds=1.,
                    teacher_recompute_fraction=.1, generation_fraction=.25, persistent_method_array_bytes=100,
                    traffic=dict(total_bytes=1000), final_metrics=metric, final_head_digest='hand_fixture',
                    public_optimizer_steps=spec.effective_steps * 2 * cfg.rounds, student_forward_endpoints=64,
                    private_optimizer_steps=300 if limit is None else 150, private_samples_per_client=[20, 20])
            return dict(partition='iid', seed=7, spec=spec.json(), config=cfg.json(), case_id=spec.case_id,
                        summary=summaries, coverage={}, metrics=[])
        out = Path(self.temp.name) / 'report'
        full, reduced = case(None, [0.3, 0.8], 10.), case(9, [0.49, 0.59], 7.)
        def read_csv(name):
            return list(csv.DictReader((out / name).read_text(encoding='utf-8').splitlines()))
        reports(out, [reduced], [])
        rows = read_csv('quality_guardrails.csv')
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(r['within_acc_guardrail'] == 'pending' for r in rows))
        reports(out, [full, reduced], [])
        rows = read_csv('quality_guardrails.csv')
        self.assertEqual(len(rows), 3)
        brow = next(r for r in rows if r['method'] == 'B')
        self.assertEqual(brow['within_acc_guardrail'], 'True')
        self.assertAlmostEqual(float(brow['acc_delta']), -0.01)
        self.assertAlmostEqual(float(brow['worst_client_acc_delta']), .19)
        costs = read_csv('paired_cost.csv')
        row = next(r for r in costs if r['case_id'] == reduced['case_id'] and r['comparison'] == 'D_over_B' and r['measure'] == 'head_pipeline_seconds')
        self.assertAlmostEqual(float(row['ratio_D_over_reference']), 1.0)
        effects = read_csv('workload_effects.csv')
        self.assertEqual(len(effects), 3)
        erow = next(r for r in effects if r['method'] == 'B')
        self.assertAlmostEqual(float(erow['head_pipeline_seconds_saved_seconds_full_minus_reduced']), 3.)
        self.assertEqual(int(erow['private_optimizer_steps_change_reduced_minus_full']), -150)


if __name__ == '__main__':
    unittest.main()
