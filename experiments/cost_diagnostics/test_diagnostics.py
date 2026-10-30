from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.certification import RelationGenerator,hard_relations
from experiments.public_scaling.config import Config
from experiments.public_scaling.engine import run_seed
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.test_scaling import fixture
from .profiler import PHASES,ProfiledGenerator
from .run import replay,same_cache,report


class Tests(unittest.TestCase):
    def test_modes_caches_ties_and_varied_changes(self):
        rng=np.random.default_rng(7)
        z=rng.normal(size=(32,7));w=rng.normal(size=(4,7));b=rng.normal(size=4)
        for degree in (1,4,8):
            graph=make_graph(32,degree,7)
            for mode in ('point','relation'):
                for zero in (False,True):
                    ww=np.zeros_like(w) if zero else w.copy();bb=np.zeros_like(b) if zero else b.copy()
                    a=RelationGenerator(z,ww,bb,graph,mode);p=ProfiledGenerator(z,ww,bb,graph,mode)
                    for step in range(8):
                        scale=(0,.0001,.03,1)[step%4]
                        ww=ww+rng.normal(size=ww.shape)*scale;bb=bb+rng.normal(size=bb.shape)*scale
                        exact=hard_relations((z@ww.T+bb).argmax(axis=1),graph)
                        ar,ast=a.generate(ww,bb);pr,pst=p.generate(ww,bb)
                        np.testing.assert_array_equal(ar,exact);np.testing.assert_array_equal(pr,exact)
                        self.assertEqual(ast,pst);same_cache(a,p)
                        self.assertEqual(set(p.phase_seconds),set(PHASES))
                        self.assertTrue(all(v>=0 for v in p.phase_seconds.values()))
                        self.assertEqual(p.diagnostics['selected_endpoints'],pst['forward_endpoints'])
                        if mode=='point':self.assertEqual(p.phase_seconds['bitsets'],0)

    def test_real_sgd_replay_against_development_reference(self):
        cfg=Config(dimensions=(6,9),public_pool=64,samples=16,degree=8,classes=3,
            rounds=4,train_limit=104,test_limit=24,pretrain_epochs=1,prepare_threads=1,
            private_batch=7,public_edge_batch=3,eval_every=1)
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            path=Path(tmp);directory=fixture(path/'fixture',cfg)
            with threadpool_limits(limits=1):
                ref=run_seed(directory,cfg,progress=False,allow_test_fixture=True)
                result=replay(directory,cfg,ref,fixture=True)
            self.assertEqual(result['mismatches'],0)
            self.assertEqual(len(result['records']),cfg.rounds*len(cfg.dimensions)*2)
            self.assertTrue(all(r['unassigned_seconds']>=0 for r in result['records']))
            report(path,[result])
            self.assertTrue((path/'report.md').exists())
            # A historical digest error must stop rather than silently rebaseline.
            ref['round_records'][next(i for i,r in enumerate(ref['round_records']) if r['method']=='E')]['head_digest_after_public']='wrong'
            with threadpool_limits(limits=1),self.assertRaises(AssertionError):
                replay(directory,cfg,ref,fixture=True)


if __name__=='__main__':unittest.main()
