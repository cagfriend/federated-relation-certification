"""Regression checks for deterministic scope and the complete wire ledger."""

from collections import Counter
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

from experiments.public_budget.student import selected_edges
from experiments.public_scaling.certification import make_matching
from experiments.public_scaling.codec import FULL, SETUP, UNKNOWN, DecodeError, Message
from experiments.snapshot_graph_scaling.design import cell_id
from ..on_demand.protocol import DemandProtocol
from .design import schedule
from .protocol import Schedule, SharedScheduleProtocol
from .worker import shared_accounting


class SharedScheduleTests(unittest.TestCase):
    def setUp(self):
        self.spec = Schedule(2024, 128, 1, 2, 16, 6, 'a'*64)
        self.args = (make_matching(128, 2024), 128, 10, (32, 32, 32, 64, 64, 64))

    def test_matches_each_node_and_accounts_for_every_byte(self):
        explicit = DemandProtocol(*self.args, adaptive=True)
        audit = []
        shared = SharedScheduleProtocol(*self.args, adaptive=True, schedule=self.spec, audit_rows=audit)
        setup = [protocol.traffic.snapshot() for protocol in (explicit, shared)]
        rounds = 3
        with patch(f'{SharedScheduleProtocol.__module__}.selected_edges', wraps=selected_edges) as sampler:
            for rnd in range(1, rounds+1):
                orders = [selected_edges(self.spec.spec(), self.spec.seed, client, rnd).astype(np.int32)
                          for client in range(6)]
                scopes = [protocol.needs(orders, rnd-1) for protocol in (explicit, shared)]
                a, b = scopes
                np.testing.assert_array_equal(a[0], b[0])
                self.assertEqual(a[0].dtype, b[0].dtype)
                for left, right in zip(a[2], b[2], strict=True):
                    np.testing.assert_array_equal(left, right)
                self.assertFalse(np.shares_memory(b[2][0], b[2][1]))
                votes = [((indices+c) % 3 == 0).astype(np.uint8) for c, indices in enumerate(a[2])]
                replies = [protocol.exchange_demand(votes, *scope[:2], rnd-1)
                           for protocol, scope in zip((explicit, shared), scopes, strict=True)]
                np.testing.assert_array_equal(replies[0][0], replies[1][0])
                np.testing.assert_array_equal(replies[0][1], replies[1][1])
        self.assertEqual(sampler.call_count, rounds*6*5)
        self.assertEqual(len(audit), rounds*6)
        results = [dict(setup_traffic=before, traffic=protocol.traffic.snapshot(),
                        traffic_breakdown=dict(protocol.breakdown), scope=[None]*rounds)
                   for protocol, before in zip((explicit, shared), setup, strict=True)]
        account = shared_accounting(*results)
        self.assertEqual(account['net_messages_saved'], (rounds-1)*2*5)
        self.assertNotIn('request_up_bytes', shared.breakdown)
        self.assertNotIn('union_down_bytes', shared.breakdown)

    def test_registration_rejects_different_public_sample_order(self):
        shared = SharedScheduleProtocol(*self.args, adaptive=True, schedule=self.spec)
        wrong = replace(self.spec, public_ids_sha256='b'*64)
        packet = Message(SETUP, FULL, 0, shared.term, UNKNOWN, UNKNOWN, 0,
                         shared.length, 6, shared.graph_id, wrong.body()).to_bytes()
        with self.assertRaisesRegex(DecodeError, 'Wrong public IDs'):
            shared.accept_schedule(packet, self.spec)

    def test_full_order_balance(self):
        cases, recaptured, blocks = schedule('full')
        counts = Counter((cell_id(b['case']), tuple(b['order'])) for b in blocks)
        self.assertEqual((len(cases), len(recaptured), len(blocks)), (12, 6, 72))
        self.assertEqual(len(counts), 72)
        self.assertEqual(set(counts.values()), {1})
