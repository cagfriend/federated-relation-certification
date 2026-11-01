import unittest

from experiments.stl10_longrun.design import checkpoints, evaluate_trajectory, plan, schedule, select_tier


def record(final_acc=0.18, final_nmi=0.05, final_clients=None, mid=None, edge=0.30, early_single=0):
    clients = final_clients if final_clients is not None else [
        dict(client=i, occupied_clusters=5, largest_cluster_fraction=0.30) for i in range(6)]
    cps = [dict(round=0, clients=clients, mean=dict(acc=0.17, nmi=0.04, ari=0.03),
                single_cluster_clients=early_single, mean_largest_cluster_fraction=0.35,
                private_pseudo_fit_mean=0.5, teacher_edge_fraction=None),
           dict(round=20, clients=(mid if mid is not None else clients),
                mean=dict(acc=0.17, nmi=0.04, ari=0.03),
                single_cluster_clients=(sum(c['occupied_clusters'] == 1 for c in mid) if mid is not None else 0),
                mean_largest_cluster_fraction=(sum(c['largest_cluster_fraction'] for c in mid) / 6 if mid is not None else 0.35),
                private_pseudo_fit_mean=0.5, teacher_edge_fraction=edge),
           dict(round=200, clients=clients, mean=dict(acc=final_acc, nmi=final_nmi, ari=0.03),
                single_cluster_clients=sum(c['occupied_clusters'] == 1 for c in clients),
                mean_largest_cluster_fraction=sum(c['largest_cluster_fraction'] for c in clients) / 6,
                private_pseudo_fit_mean=0.5, teacher_edge_fraction=edge)]
    return dict(rounds=200, checkpoints=cps,
                round_records=[dict(round=200, positive_relation_fraction=edge)])


class CheckpointTests(unittest.TestCase):
    def test_full_checkpoint_set(self):
        self.assertEqual(checkpoints(200), [0, 1, 2, 5, 10, 20, 40, 60, 80, 100, 120, 140, 160, 180, 200])

    def test_smoke_checkpoint_set(self):
        self.assertEqual(checkpoints(12), [0, 1, 2, 5, 10, 12])


class CriteriaTests(unittest.TestCase):
    def test_healthy_trajectory_passes(self):
        self.assertTrue(evaluate_trajectory(record())['passed'])

    def test_one_dominant_client_fails_s1_even_when_mean_is_fine(self):
        clients = [dict(client=0, occupied_clusters=2, largest_cluster_fraction=0.995)] + [
            dict(client=i, occupied_clusters=6, largest_cluster_fraction=0.20) for i in range(1, 6)]
        verdict = evaluate_trajectory(record(final_clients=clients))
        self.assertFalse(verdict['S1'])
        self.assertFalse(verdict['passed'])

    def test_single_cluster_client_fails_s1(self):
        clients = [dict(client=i, occupied_clusters=5, largest_cluster_fraction=0.30) for i in range(6)]
        clients[3] = dict(client=3, occupied_clusters=1, largest_cluster_fraction=1.0)
        self.assertFalse(evaluate_trajectory(record(final_clients=clients))['S1'])

    def test_early_single_cluster_is_warning_only_for_s2(self):
        self.assertTrue(evaluate_trajectory(record(early_single=3))['S2'])

    def test_round20_mass_collapse_fails_s2(self):
        mid = [dict(client=i, occupied_clusters=1, largest_cluster_fraction=1.0) for i in range(4)] + [
            dict(client=i, occupied_clusters=5, largest_cluster_fraction=0.30) for i in range(4, 6)]
        self.assertFalse(evaluate_trajectory(record(mid=mid))['S2'])

    def test_quality_floor_and_edge_fraction(self):
        self.assertFalse(evaluate_trajectory(record(final_acc=0.10))['Q1'])
        self.assertFalse(evaluate_trajectory(record(final_nmi=0.002))['Q1'])
        self.assertFalse(evaluate_trajectory(record(edge=0.999))['Q2'])


class SelectionTests(unittest.TestCase):
    def test_both_validated_selects_two(self):
        self.assertEqual(select_tier({1: [True] * 4, 2: [True] * 4}), 2)

    def test_only_two_validated_selects_two(self):
        self.assertEqual(select_tier({1: [True, True, False, True], 2: [True] * 4}), 2)

    def test_only_one_validated_selects_one(self):
        self.assertEqual(select_tier({1: [True] * 4, 2: [True, False, True, True]}), 1)

    def test_neither_validated_returns_none(self):
        self.assertIsNone(select_tier({1: [False] * 4, 2: [True, True, True, False]}))


class PlanTests(unittest.TestCase):
    def test_full_matrix_is_eight_trajectories(self):
        self.assertEqual(len(schedule('full')), 8)
        self.assertEqual({s.steps for s in plan('full')}, {1, 2})

    def test_smoke_matrix(self):
        self.assertEqual(len(schedule('smoke')), 4)


if __name__ == '__main__':
    unittest.main()
