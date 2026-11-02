import copy
import unittest
from unittest.mock import patch
import numpy as np
from experiments.k_scaling.design import plan,schedule,filename
from experiments.k_scaling.run import verify_groups,non_time_rows
from experiments.public_scaling.certification import RelationGenerator,hard_relations
from experiments.stl10_compute.run import TRAJECTORY_KEYS

class DesignTests(unittest.TestCase):
    def test_full_matrix_and_memory_subset(self):
        self.assertEqual(len(schedule('full')),72)
        self.assertEqual(len({filename(m) for m in schedule('full')}),72)
        m=schedule('full',True);self.assertEqual(len(m),12)
        self.assertEqual({x['classes'] for x in m},{10,64})
        self.assertEqual({x['seed'] for x in m},{1002})
        self.assertEqual(len(schedule('smoke')),18)
    def test_features_and_private_budget_fixed(self):
        specs=plan('full');prep=[]
        for s in specs:
            self.assertIsNone(s.private_limit);self.assertEqual(s.steps,2)
            p=s.config.preparation();p.pop('classes');prep.append(p)
        self.assertTrue(all(p==prep[0] for p in prep))

class ExactnessTests(unittest.TestCase):
    def test_k64_and_intermediate_certificate_results(self):
        rng=np.random.default_rng(501)
        x=rng.normal(size=(32,7));edges=np.arange(32,dtype=np.uint32).reshape(-1,2)
        for k in (10,16,32,64):
            w=rng.normal(size=(k,7));b=rng.normal(size=k)
            generators=[RelationGenerator(x,w,b,edges,mode) for mode in ('full','point','relation')]
            for _ in range(8):
                w=w+rng.normal(scale=.003,size=w.shape);b=b+rng.normal(scale=.003,size=b.shape)
                expected=hard_relations((x@w.T+b).argmax(axis=1),edges)
                for g in generators:
                    actual,_=g.generate(w,b);np.testing.assert_array_equal(actual,expected)
    def test_changed_public_trajectory_rejected(self):
        completed=[]
        for method in ('B','E','D'):
            row={k:0 for k in TRAJECTORY_KEYS}
            r=dict(initial_head_digest='a',graph_sha256='g',round_records=[row],metrics=[])
            completed.append((dict(partition='iid',seed=1001,classes=16,method=method),r))
        verify_groups(completed)
        bad=copy.deepcopy(completed);bad[-1][1]['round_records'][0]['head_digest_after_public']='wrong'
        with self.assertRaises(ValueError):verify_groups(bad)
    def test_memory_counter_changes_not_hidden_by_timing_filter(self):
        a=dict(round_records=[dict(generation_seconds=1.,teacher_forward_endpoints=5)])
        b=dict(round_records=[dict(generation_seconds=9.,teacher_forward_endpoints=5)])
        self.assertEqual(non_time_rows(a),non_time_rows(b))
        b['round_records'][0]['teacher_forward_endpoints']=6
        self.assertNotEqual(non_time_rows(a),non_time_rows(b))

if __name__=='__main__':unittest.main()
