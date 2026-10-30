import copy
from dataclasses import asdict,replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
from experiments.public_scaling.codec import UP,encode_vector,DecodeError
from experiments.public_scaling.protocol import RelationProtocol
from experiments.public_scaling.util import seal_payload
from .protocol import POLICIES,RecoveryProtocol
from .run import Case,traces,simulate,check_case,report


class Tests(unittest.TestCase):
    def setUp(self):
        self.cfg=Case(name='test',samples=32,rounds=8,degree=8,event='crash_down',rejoin_after=2)
        self.graph,self.trace=traces(self.cfg,7)
        self.dimensions=(512,512,512,2048,2048,2048)

    def assert_targets(self,p,current):
        expected=np.sum([current[c] for c in p.active],axis=0,dtype=np.int64)
        for c in p.active:
            np.testing.assert_array_equal(p.nodes[c].counts,expected)
            np.testing.assert_array_equal(p.nodes[p.leader].rows[c],current[c])
            self.assertIsNone(p.nodes[c].pending)

    def test_normal_matches_original_targets_and_counted_wire(self):
        old=RelationProtocol(self.graph,32,10,self.dimensions,adaptive=True)
        for policy in POLICIES:
            p=RecoveryProtocol(self.graph,32,self.dimensions,policy)
            p.capture=True
            before=dict(p.ledger)
            for current in self.trace:
                self.assertTrue(p.exchange(current));self.assert_targets(p,current)
            self.assertEqual(p.ledger['bytes']-before['bytes'],sum(len(packet) for packet,_,_,_ in p.sent_packets))
            self.assertEqual(p.ledger['messages']-before['messages'],len(p.sent_packets))
            self.assertTrue(all(src!=dst for _,src,dst,_ in p.sent_packets))
        for current in self.trace:old.exchange(current)
        for c in old.client_counts:np.testing.assert_array_equal(c,p.nodes[0].counts)

    def test_failure_pending_rollback_membership_rejoin_and_no_hidden_cache(self):
        for fault in ('crash_upload','crash_down'):
            for policy in POLICIES:
                p=RecoveryProtocol(self.graph,32,self.dimensions,policy)
                p.exchange(self.trace[0]);oldcounts=[n.counts.copy() for n in p.nodes]
                oldrows={c:v.copy() for c,v in p.nodes[1].rows.items()}
                self.assertFalse(p.exchange(self.trace[1],fault=fault))
                self.assertEqual(p.version,0)
                for n,c in zip(p.nodes,oldcounts):np.testing.assert_array_equal(n.counts,c)
                old=p.transition(fault)
                self.assertEqual(old,0);self.assertEqual(p.leader,1);self.assertEqual(p.term,2)
                self.assertNotIn(0,p.active);self.assertIsNone(p.nodes[0].own)
                self.assertEqual(p.nodes[0].rows,{})
                if policy=='hot_backup':
                    for c in p.active:np.testing.assert_array_equal(p.nodes[1].rows[c],oldrows[c])
                else:self.assertEqual(p.nodes[1].rows,{})
                self.assertTrue(all(n.pending is None for n in p.nodes))
                p.exchange(self.trace[1]);self.assert_targets(p,self.trace[1]);self.assertEqual(p.version,1)
                p.rejoin(0);self.assertIsNone(p.nodes[0].own)
                p.exchange(self.trace[2]);self.assert_targets(p,self.trace[2]);self.assertEqual(len(p.active),6)

    def test_handoff_transferred_state_and_replication_cost_not_free(self):
        for policy in POLICIES:
            p=RecoveryProtocol(self.graph,32,self.dimensions,policy);p.exchange(self.trace[0])
            oldversion=p.version;p.transition('handoff')
            self.assertEqual(p.active,list(range(6)));self.assertEqual(p.version,oldversion)
            if policy=='on_demand':
                self.assertGreater(p.ledger['handoff_bytes'],0)
                for c in p.active:np.testing.assert_array_equal(p.nodes[p.leader].rows[c],self.trace[0][c])
            p.exchange(self.trace[1]);self.assert_targets(p,self.trace[1])
            self.assertEqual(p.version,1)
            if policy=='hot_backup':self.assertGreater(p.ledger['replication_bytes'],0)
            else:self.assertEqual(p.ledger.get('replication_bytes',0),0)

    def test_duplicate_conflict_stale_term_and_departed_sender(self):
        p=RecoveryProtocol(self.graph,32,self.dimensions,'rebuild');p.exchange(self.trace[0]);p.rollback()
        old=p.nodes[1].own
        first=old.copy();first[0]^=1
        def encode(value,term):return encode_vector(value,old,kind=UP,adaptive=True,
            graph_id=p.graph_id,sender=1,base=0,target=1,maximum=1,term=term)
        packet=encode(first,1);p.accept_upload(packet,1);p.accept_upload(packet,1)
        self.assertEqual(len(p.staged),1)
        second=first.copy();second[1]^=1
        with self.assertRaises(DecodeError):p.accept_upload(encode(second,1),1)
        p.transition('handoff')
        # Client1 became leader; use another sender to isolate term fencing.
        stale=encode_vector(first,p.nodes[2].own,kind=UP,adaptive=True,graph_id=p.graph_id,
                            sender=2,base=0,target=1,maximum=1,term=1)
        with self.assertRaises(DecodeError):p.accept_upload(stale,2)
        before=dict(p.ledger)
        with self.assertRaises(DecodeError):p._wire(stale,2,p.leader)
        self.assertEqual(before,dict(p.ledger))
        p.transition('crash_upload')
        with self.assertRaises(DecodeError):p.accept_upload(packet,1)

    def test_replica_encoder_does_not_use_remote_reference(self):
        p=RecoveryProtocol(self.graph,32,self.dimensions,'hot_backup')
        p.exchange(self.trace[0])
        # Corrupt only the backup's private state. A sender reading that remote
        # reference to create its delta would mask this mismatch; ours must stop.
        p.nodes[p.backup].rows[0][0]^=1
        with self.assertRaises(DecodeError):p.exchange(self.trace[0])

    def test_all_scenarios_saved_oracle_and_corrupt_record_rejected(self):
        from .run import plan
        for cfg in plan('smoke'):
            graph,trace=traces(cfg,7)
            methods=[simulate(cfg,7,p,graph,trace) for p in POLICIES]
            identity={'test':True};case=seal_payload(dict(config=asdict(cfg),seed=7,methods=methods,identity=identity))
            check_case(case,cfg,7,identity,trace)
            bad=copy.deepcopy(case);bad['methods'][0]['round_records'][2]['target_denominator']=99
            with self.assertRaises(ValueError):check_case(seal_payload(bad),cfg,7,identity,trace)
            bad=copy.deepcopy(case);bad['methods'][0]['traffic']['bytes']+=1
            with self.assertRaises(ValueError):check_case(seal_payload(bad),cfg,7,identity,trace)
            bad=copy.deepcopy(case);bad['methods'][0]['round_records'][0]['traffic']['bytes']+=1
            with self.assertRaises(ValueError):check_case(seal_payload(bad),cfg,7,identity,trace)
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
                report(Path(tmp),[case]);self.assertTrue((Path(tmp)/'summary.json').is_file())


if __name__=='__main__':unittest.main()
