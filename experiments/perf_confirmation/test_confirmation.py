"""Unit tests for the confirmation design, identity checks and decisions."""
import copy
import unittest
from .design import plan, schedule, method_order, CONFIRM_SEEDS, REPEATS, METHODS
from .engine import check_block_identity
from .report import aggregate, paired_summary, decide

TRAJ = dict(head_digest_after_public='h', public_schedule_digest='s',
            public_optimizer_steps=48, student_forward_endpoints=100,
            public_edges_consumed=800, committed_counts_digest='c',
            received_counts_digests=['c'], private_loss=1.0, public_loss=2.0,
            private_subset_digest='d', private_samples_per_client=[10],
            private_subset_pseudo_histograms=[[10]], private_optimizer_steps=5,
            private_forward_endpoints=60, positive_relation_fraction=0.5,
            traffic={'a': 1})
METH = dict(teacher_forward_endpoints=10, certified_edges_before_refresh=3,
            client_statistics=[], persistent_method_array_bytes=7)


def fake_run(part='iid', seed=707, case_id='m16384_fixed8_priv2048', method='B',
             repeat=0, head=100.0, acc=0.5):
    row = dict(method=method, round=1, **TRAJ, **METH,
               private_seconds=1.0, generation_seconds=2.0, exchange_seconds=0.1,
               public_seconds=3.0, pipeline_seconds=6.1)
    summary = dict(initialization_seconds=1.0, head_pipeline_seconds=head,
                   with_shared_preparation_seconds=head + 10.0,
                   private_seconds=40.0, generation_seconds=head * 0.3,
                   exchange_seconds=1.0, public_seconds=50.0,
                   generation_fraction=0.3, teacher_recompute_fraction=0.5,
                   persistent_method_array_bytes=7, initial_traffic={}, traffic={'a': 200},
                   public_optimizer_steps=9600, student_forward_endpoints=20000,
                   private_optimizer_steps=1000, private_forward_endpoints=12000,
                   final_head_digest='h',
                   final_metrics=dict(round=200, method=method, clients=[],
                                      mean=dict(acc=acc, nmi=0.4, ari=0.3)))
    return dict(partition=part, seed=seed, case_id=case_id, method=method, repeat=repeat,
                triple=0, position=0, process_wall_seconds=10.0, process_peak_bytes=123,
                initial_head_digest='i', graph_sha256='g', summary={method: summary},
                round_records=[row],
                metrics=[dict(round=200, method=method, clients=[], mean=dict(acc=acc, nmi=0.4, ari=0.3))],
                coverage={}, coverage_records=[dict(round=1)],
                validation=dict(enabled=True, mismatches=0, relation_comparisons=10,
                                candidate_membership_comparisons=20))


class Tests(unittest.TestCase):
    def test_plan_tiers_frozen(self):
        self.assertEqual([s.private_limit for s in plan('full')], [None, 2048])
        self.assertEqual([s.private_limit for s in plan('smoke')], [None, 128])
        self.assertEqual(CONFIRM_SEEDS, (707, 808, 909))
        self.assertEqual(REPEATS, (0, 1))

    def test_schedule_balance(self):
        runs = schedule('full')
        self.assertEqual(len(runs), 72)
        triples = {}
        for r in runs:
            triples.setdefault(r['triple'], []).append(r)
        self.assertEqual(len(triples), 24)
        leads = [sorted(v, key=lambda x: x['position'])[0]['method'] for v in triples.values()]
        self.assertEqual({m: leads.count(m) for m in METHODS}, {m: 8 for m in METHODS})
        self.assertEqual(method_order(0), METHODS)
        self.assertEqual(method_order(1), ('E', 'D', 'B'))

    def test_block_identity_and_tamper(self):
        runs = [fake_run(method=m, repeat=r) for m in METHODS for r in REPEATS]
        self.assertEqual(check_block_identity(runs)['mismatches'], 0)
        bad = copy.deepcopy(runs)
        bad[3]['round_records'][0]['head_digest_after_public'] = 'tampered'
        with self.assertRaises(AssertionError):
            check_block_identity(bad)
        drift = copy.deepcopy(runs)
        drift[1]['round_records'][0]['teacher_forward_endpoints'] = 99
        with self.assertRaises(AssertionError):
            check_block_identity(drift)

    def test_aggregation_and_decision(self):
        runs = []
        for part in ('iid', 'dirichlet_0.1'):
            for seed in CONFIRM_SEEDS:
                for cid, scale in (('m16384_fixed8_privfull', 1.3), ('m16384_fixed8_priv2048', 1.0)):
                    for method, head in (('B', 100.0), ('E', 80.0), ('D', 70.0)):
                        for rep in REPEATS:
                            runs.append(fake_run(part=part, seed=seed, case_id=cid, method=method,
                                                 repeat=rep, head=head * scale,
                                                 acc=0.5 if scale == 1.3 else 0.495))
        _, _, paired, noise, guardrails = aggregate(runs)
        verdicts = decide(paired_summary(paired))
        self.assertEqual(len(verdicts), 2)
        self.assertTrue(all(v['confirmed'] for v in verdicts))
        self.assertEqual(len(guardrails), 6)
        self.assertTrue(all(g['within_guardrail'] for g in guardrails))
        self.assertTrue(noise and all(n['repeat_relative_difference'] == 0 for n in noise))
        failing = copy.deepcopy(paired_summary(paired))
        for row in failing:
            if row['comparison'] == 'D_over_E':
                row['head_pipeline_seconds_median_ratio'] = 1.05
        self.assertFalse(any(v['confirmed'] for v in decide(failing)))


if __name__ == '__main__':
    unittest.main()
