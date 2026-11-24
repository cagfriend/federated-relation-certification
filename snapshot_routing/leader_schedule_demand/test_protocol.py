"""Verify that only request upload leaves the per-round wire ledger."""

import unittest
from unittest.mock import patch

import numpy as np

from experiments.public_budget.student import selected_edges
from experiments.public_scaling.certification import make_matching
from ..on_demand.protocol import DemandProtocol
from ..shared_schedule_demand.protocol import Schedule
from .protocol import LeaderScheduleProtocol
from .worker import leader_accounting


class LeaderScheduleTests(unittest.TestCase):
    def test_scope_and_exact_wire_accounting(self):
        cfg = Schedule(2024, 4096, 1, 2, 64, 6, 'a'*64)
        args = (make_matching(cfg.samples, cfg.seed), cfg.samples, 10, (128, 128, 128, 256, 256, 256))
        explicit = DemandProtocol(*args, adaptive=True)
        audit = []
        leader = LeaderScheduleProtocol(*args, adaptive=True, schedule=cfg, audit_rows=audit)
        setup = [p.traffic.snapshot() for p in (explicit, leader)]
        rounds = 3
        with patch(f'{LeaderScheduleProtocol.__module__}.selected_edges', wraps=selected_edges) as sampler:
            for rnd in range(1, rounds+1):
                orders = [selected_edges(cfg.spec(), cfg.seed, peer, rnd).astype(np.int32)
                          for peer in range(cfg.members)]
                scopes = [p.needs(orders, rnd-1) for p in (explicit, leader)]
                first, second = scopes
                self.assertEqual(first[0].dtype, second[0].dtype)
                np.testing.assert_array_equal(first[0], second[0])
                for a, b in zip(first[2], second[2], strict=True):
                    np.testing.assert_array_equal(a, b)
                votes = [((ids+peer) % 4 == 0).astype(np.uint8) for peer, ids in enumerate(first[2])]
                old, new = [p.exchange_demand(votes, *scope[:2], rnd-1)
                            for p, scope in zip((explicit, leader), scopes, strict=True)]
                np.testing.assert_array_equal(old[0], new[0])
                np.testing.assert_array_equal(old[1], new[1])
        self.assertEqual(sampler.call_count, rounds*(cfg.members-1))
        self.assertEqual([(r['round'], r['client'], r['peer_orders']) for r in audit],
                         [(rnd, 0, cfg.members-1) for rnd in range(1, rounds+1)])
        summaries = [dict(setup_traffic=initial, traffic=p.traffic.snapshot(),
                          traffic_breakdown=dict(p.breakdown), scope=[None]*rounds)
                     for p, initial in zip((explicit, leader), setup, strict=True)]
        account = leader_accounting(*summaries)
        self.assertEqual(account['request_up_removed'], 1125*rounds)
        self.assertEqual(account['union_down_retained'], 1525*rounds)
        self.assertEqual(account['net_messages_saved'], 5*rounds-10)
        self.assertNotIn('request_up_bytes', leader.breakdown)

    def test_audit_rejects_wrong_remote_student_order(self):
        cfg = Schedule(2024, 128, 1, 2, 16, 2, 'a'*64)
        leader = LeaderScheduleProtocol(make_matching(128, 2024), 128, 10, (32, 64),
                                        adaptive=True, schedule=cfg, audit_rows=[])
        orders = [selected_edges(cfg.spec(), cfg.seed, peer, 1) for peer in range(2)]
        orders[1] = orders[1][::-1]
        with self.assertRaisesRegex(ValueError, 'differ from student orders'):
            leader.needs(orders, 0)
