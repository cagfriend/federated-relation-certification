import unittest

from experiments.stl10_compute.design import guardrail, plan, schedule
from experiments.stl10_compute.report import aggregate


def clients(single=0, largest=0.30):
    out = []
    for i in range(6):
        if i < single:
            out.append(dict(client=i, occupied_clusters=1, largest_cluster_fraction=1.0,
                            acc=0.1, nmi=0.0, ari=0.0, cluster_counts=[8000] + [0] * 9))
        else:
            out.append(dict(client=i, occupied_clusters=5, largest_cluster_fraction=largest,
                            acc=0.20, nmi=0.10, ari=0.05, cluster_counts=[2400] + [700] * 8))
    return out


def b_record(single=0, acc=0.20, nmi=0.10, edge=0.13):
    cs = clients(single)
    metrics = [dict(round=r, method='B', clients=cs,
                    mean=dict(acc=acc, nmi=nmi, ari=0.05)) for r in range(20, 201, 20)]
    rounds = [dict(round=r, positive_relation_fraction=edge) for r in range(1, 201)]
    return dict(metrics=metrics, round_records=rounds)


class GuardrailTests(unittest.TestCase):
    def test_healthy_record_passes(self):
        self.assertTrue(guardrail(b_record())['passed'])

    def test_collapsed_record_fails(self):
        verdict = guardrail(b_record(single=6, acc=0.10, nmi=0.0, edge=0.999))
        self.assertFalse(verdict['S1'])
        self.assertFalse(verdict['Q1'])
        self.assertFalse(verdict['Q2'])
        self.assertFalse(verdict['passed'])


def run_record(method, head, gen, acc=0.20):
    return dict(seed=1001, partition='iid', case_id='m128_fixed2_privfull', method=method,
                process_peak_bytes=1000,
                summary={method: dict(head_pipeline_seconds=head, generation_seconds=gen,
                                      private_seconds=1.0, public_seconds=1.0,
                                      with_shared_preparation_seconds=head + 100.0,
                                      generation_fraction=gen / head, teacher_recompute_fraction=0.07,
                                      student_forward_endpoints=10, private_forward_endpoints=20,
                                      traffic=dict(total_bytes=500),
                                      persistent_method_array_bytes=2048,
                                      final_metrics=dict(mean=dict(acc=acc, nmi=0.1, ari=0.05)))})


class AggregateTests(unittest.TestCase):
    def test_paired_ratios_and_wins(self):
        runs = [run_record('B', 100.0, 60.0), run_record('E', 80.0, 40.0), run_record('D', 70.0, 30.0)]
        rows, paired, summary = aggregate(runs)
        self.assertEqual(len(rows), 3)
        db = next(x for x in summary if x['comparison'] == 'D/B')
        self.assertAlmostEqual(db['median_head_ratio'], 0.7)
        self.assertAlmostEqual(db['median_saved_seconds'], 30.0)
        self.assertEqual(db['head_wins'], 1)
        de = next(x for x in summary if x['comparison'] == 'D/E')
        self.assertAlmostEqual(de['median_head_ratio'], 0.875)


class PlanTests(unittest.TestCase):
    def test_full_matrix_is_18_runs_6_triples(self):
        s = schedule('full')
        self.assertEqual(len(s), 18)
        self.assertEqual(len({x['triple'] for x in s}), 6)
        self.assertEqual(plan('full')[0].steps, 2)
        self.assertEqual(plan('full')[0].case_id, 'm16384_fixed2_privfull')

    def test_smoke_matrix_is_6_runs(self):
        self.assertEqual(len(schedule('smoke')), 6)


if __name__ == '__main__':
    unittest.main()
