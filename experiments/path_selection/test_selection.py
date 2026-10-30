import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.public_scaling.certification import RelationGenerator, hard_relations
from experiments.public_scaling.config import Config
from experiments.public_scaling.engine import run_seed
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.test_scaling import fixture
from experiments.public_scaling.util import seal_payload
from .selection import POLICIES, PolicyGenerator, choose
from .run import cache_digest, check_case, replay, report


class Tests(unittest.TestCase):
    def test_rule_and_bootstrap(self):
        self.assertEqual(choose('adaptive', 1, 2048, None), 'D')
        self.assertEqual(choose('adaptive', 8, 2048, None), 'E')
        self.assertEqual(choose('adaptive', 1, 2048, .15), 'D')
        self.assertEqual(choose('adaptive', 1, 2048, .15001), 'E')
        self.assertEqual(choose('adaptive', 1, 512, .15), 'E')
        self.assertEqual(choose('adaptive', 8, 2048, .01), 'D')
        self.assertEqual(choose('static', 1, 1, 1), 'D')
        self.assertEqual(choose('static', 4, 2048, 0), 'E')

    def test_switching_continuous_cache_oracle_and_single_path(self):
        rng=np.random.default_rng(820)
        schedules=[['E','D']*10, ['D']*8+['E']*6+['D']*6]
        for degree in (1,4,8):
            for integer in (False,True):
                for schedule in schedules:
                    z=rng.integers(-2,3,(32,7)) if integer else rng.normal(size=(32,7))
                    w=np.zeros((4,7),dtype=np.int64 if integer else np.float64)
                    b=np.zeros(4,dtype=w.dtype)
                    graph=make_graph(32,degree,7)
                    g=PolicyGenerator(z,w,b,graph,'adaptive',degree,exact_integer=integer)
                    shadow=RelationGenerator(z,w,b,graph,'point',exact_integer=integer)
                    original_arrays={k:id(getattr(g,k)) for k in ('gaps','winners','weight_at','bias_at','last_evaluated')}
                    previous=None
                    for step,path in enumerate(schedule):
                        # Zero movement/ties, small/large changes and reversals.
                        if integer:
                            if step%4: w=w+rng.integers(-3,4,w.shape); b=b+rng.integers(-3,4,b.shape)
                        else:
                            scale=(0,1e-6,.03,5)[step%4]
                            w=w+rng.normal(size=w.shape)*scale; b=b+rng.normal(size=b.shape)*scale
                        if step==11: w=-w; b=-b
                        with patch('experiments.path_selection.selection.choose',return_value=path) as decision:
                            relation,stats=g.generate(w,b)
                            decision.assert_called_once_with('adaptive',degree,7,previous)
                        shadow.mode='point' if path=='E' else 'relation'
                        expected,base_stats=shadow.generate(w,b)
                        labels=(z@w.T+b).argmax(axis=1)
                        np.testing.assert_array_equal(relation,hard_relations(labels,graph))
                        np.testing.assert_array_equal(relation,expected)
                        self.assertEqual(cache_digest(g),cache_digest(shadow))
                        self.assertEqual({k:stats[k] for k in base_stats},base_stats)
                        self.assertTrue(np.all(g.candidate_matrix()[np.arange(len(z)),labels]))
                        self.assertEqual(stats['previous_refresh_fraction'],previous)
                        previous=stats['forward_endpoints']/len(z)
                    self.assertEqual(g.round,len(schedule))
                    self.assertEqual(original_arrays,{k:id(getattr(g,k)) for k in original_arrays})
                    self.assertEqual(g.switches,sum(a!=b for a,b in zip(schedule,schedule[1:])))

    def test_fixed_policy_equivalence_k64(self):
        rng=np.random.default_rng(54); z=rng.normal(size=(16,9));graph=make_graph(16,8,9)
        for k in (2,10,64):
            for policy,mode in (('E','point'),('D','relation')):
                w=rng.normal(size=(k,9));b=rng.normal(size=k)
                g=PolicyGenerator(z,w,b,graph,policy,8);shadow=RelationGenerator(z,w,b,graph,mode)
                for _ in range(5):
                    w=w+rng.normal(size=w.shape)*.01;b=b+rng.normal(size=b.shape)*.01
                    a,stats=g.generate(w,b); bb,expected=shadow.generate(w,b)
                    np.testing.assert_array_equal(a,bb)
                    self.assertEqual({k:stats[k] for k in expected},expected)
                    self.assertEqual(cache_digest(g),cache_digest(shadow))

    def test_sgd_replay_resume_validation_and_corruption(self):
        cfg=Config(dimensions=(6,9),public_pool=64,samples=16,degree=8,classes=3,
                   rounds=6,train_limit=104,test_limit=24,pretrain_epochs=1,prepare_threads=1,
                   private_batch=7,public_edge_batch=3,eval_every=2)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root=Path(tmp);directory=fixture(root/'fixture',cfg)
            with threadpool_limits(limits=1):
                reference=run_seed(directory,cfg,progress=False,allow_test_fixture=True)
                result=replay(directory,cfg,reference,fixture=True)
            identity={'unit_test':True}
            case=seal_payload(dict(**result,identity=identity))
            check_case(case,cfg,7,identity,reference)
            report(root,[case])
            self.assertTrue((root/'summary.json').is_file())
            self.assertEqual(len(result['records']),cfg.rounds*2*len(POLICIES))
            # Static equals E at degree 8, including its continuous cache history.
            bykey={(r['round'],r['client'],r['policy']):r for r in result['records']}
            for rnd in range(1,cfg.rounds+1):
                for c in range(2):
                    self.assertEqual(bykey[(rnd,c,'E')]['cache_digest'],bykey[(rnd,c,'static')]['cache_digest'])
            for field in ('previous_refresh_fraction','selected_path','switched'):
                bad=copy.deepcopy(case)
                row=next(r for r in bad['records'] if r['round']==3 and r['policy']=='adaptive')
                row['statistics'][field]='corrupt'
                bad=seal_payload(bad)
                with self.assertRaises(ValueError):check_case(bad,cfg,7,identity,reference)
            bad=copy.deepcopy(case);bad['records'].pop();bad=seal_payload(bad)
            with self.assertRaises(ValueError):check_case(bad,cfg,7,identity,reference)
            bad=copy.deepcopy(case);bad['training'][0]['head_digest']='wrong';bad=seal_payload(bad)
            with self.assertRaises(ValueError):check_case(bad,cfg,7,identity,reference)
            badref=copy.deepcopy(reference)
            next(r for r in badref['round_records'] if r['method']=='E')['head_digest_after_public']='wrong'
            with threadpool_limits(limits=1), self.assertRaises(AssertionError):
                replay(directory,cfg,badref,fixture=True)


if __name__=='__main__': unittest.main()
