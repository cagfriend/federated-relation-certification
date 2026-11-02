import copy
import unittest

from experiments.stl10_compute.run import TRAJECTORY_KEYS
from experiments.stl10_repeat_confirmation.design import REPEATS, schedule, summarize
from experiments.stl10_repeat_confirmation.run import verify_blocks

CLIENT = dict(acc=0.20, nmi=0.10, ari=0.05, occupied_clusters=5,
              largest_cluster_fraction=0.30, cluster_counts=[2400] + [700] * 8)


def make_record(method, head, rounds=200):
    rows = []
    for i in range(1, rounds + 1):
        row = {k: 0 for k in TRAJECTORY_KEYS}
        row.update(round=i, positive_relation_fraction=0.13, private_loss=1.0, public_loss=1.0)
        rows.append(row)
    metrics = [dict(round=r, method=method, mean=dict(acc=0.20, nmi=0.10, ari=0.05),
                    clients=[dict(client=c, **CLIENT) for c in range(6)])
               for r in range(20, rounds + 1, 20)]
    return dict(seed=1001, partition='iid', method=method, initial_head_digest='h', graph_sha256='g',
                round_records=rows, metrics=metrics,
                summary={method: dict(head_pipeline_seconds=head)},
                validation=dict(relation_comparisons=100,
                                candidate_membership_comparisons=0 if method == 'B' else 50))


def block(seed=1001, part='iid', heads=None):
    heads = heads or {'B': 100.0, 'E': 80.0, 'D': 70.0}
    out = []
    for method in ('B', 'E', 'D'):
        for rep in range(REPEATS):
            meta = dict(seed=seed, partition=part, case_id='x', method=method, repeat=rep)
            out.append((meta, make_record(method, heads[method])))
    return out


def longrun_anchor(record):
    cps = [dict(round=m['round'], mean=m['mean'], clients=m['clients']) for m in record['metrics']]
    return dict(round_records=record['round_records'], checkpoints=cps)


class ScheduleTests(unittest.TestCase):
    def test_full_matrix_54_and_balanced_leadership(self):
        s = schedule('full')
        self.assertEqual(len(s), 54)
        from collections import Counter
        leads = Counter()
        for meta in s:
            if meta['position'] == 0:
                leads[(meta['partition'], meta['seed'], meta['method'])] += 1
        self.assertTrue(all(v == 1 for v in leads.values()))
        self.assertEqual(len(leads), 18)

    def test_smoke_matrix_18(self):
        self.assertEqual(len(schedule('smoke')), 18)


class SummarizeTests(unittest.TestCase):
    def test_verdicts_pass_and_noise(self):
        runs = []
        for seed in (1001, 1002, 1003):
            for meta, record in block(seed=seed):
                record['seed'] = seed
                runs.append((dict(meta, seed=seed), record))
        noise, seed_rows, verdicts = summarize(runs)
        self.assertEqual(len(noise), 9)  # 3 seeds x 3 methods, iid only in this fixture
        self.assertTrue(verdicts['iid']['confirmed'])
        self.assertAlmostEqual(verdicts['iid']['median_ratio_DE'], 0.875)

    def test_c2_fails_when_d_not_faster_than_e(self):
        runs = []
        for seed in (1001, 1002, 1003):
            for meta, record in block(seed=seed, heads={'B': 100.0, 'E': 60.0, 'D': 70.0}):
                runs.append((dict(meta, seed=seed), record))
        _, _, verdicts = summarize(runs)
        self.assertFalse(verdicts['iid']['C2'])
        self.assertFalse(verdicts['iid']['confirmed'])


class VerifyBlocksTests(unittest.TestCase):
    def setUp(self):
        self.items = block()
        base = self.items[0][1]
        self.compute_anchor = {(1001, 'iid'): make_record('B', 100.0)}
        self.long_anchor = {(1002, 'iid'): longrun_anchor(make_record('B', 100.0))}

    def test_valid_block_passes_and_guardrail_ok(self):
        guards = verify_blocks(self.items, {}, {}, self.compute_anchor, fixture=False)
        self.assertEqual(len(guards), 1)
        self.assertTrue(guards[0]['passed'])

    def test_missing_compute_anchor_is_hard_failure(self):
        with self.assertRaises(ValueError):
            verify_blocks(self.items, {}, {}, {}, fixture=False)

    def test_tampered_trajectory_rejected(self):
        items = copy.deepcopy(self.items)
        items[5][1]['round_records'][10]['private_loss'] = 9.9
        with self.assertRaises(ValueError):
            verify_blocks(items, {}, {}, self.compute_anchor, fixture=False)

    def test_longrun_anchor_enforced_for_anchored_seed(self):
        items = block(seed=1002)
        with self.assertRaises(ValueError):
            verify_blocks(items, {}, {}, {(1002, 'iid'): make_record('B', 100.0)}, fixture=False)
        guards = verify_blocks(items, {}, self.long_anchor, {(1002, 'iid'): make_record('B', 100.0)}, fixture=False)
        self.assertTrue(guards[0]['passed'])

    def test_tampered_longrun_anchor_rejected(self):
        items = block(seed=1002)
        bad = copy.deepcopy(self.long_anchor)
        bad[(1002, 'iid')]['round_records'][3]['private_loss'] = 7.7
        with self.assertRaises(ValueError):
            verify_blocks(items, {}, bad, {(1002, 'iid'): make_record('B', 100.0)}, fixture=False)


if __name__ == '__main__':
    unittest.main()
