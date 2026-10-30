import gzip
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling import data as core
from experiments.public_scaling.config import Config
from experiments.public_scaling.head import Head,private_epoch
from experiments.public_scaling.engine import heads_digest
from experiments.public_scaling.test_scaling import fixture
from . import data
from .engine import run
from .report import reports


class Tests(unittest.TestCase):
    def test_balanced_partitions_coverage_determinism_and_histograms(self):
        labels=np.arange(60000,dtype=np.int64)%10
        for seed in (404,505,606):
            common=None
            for partition in data.PARTITIONS:
                public,private,diag=data.partition_indices(labels,16384,6,seed,partition)
                np.testing.assert_array_equal(np.sort(np.concatenate([public,*private])),np.arange(60000))
                self.assertEqual(list(map(len,private)),[7270,7270,7269,7269,7269,7269])
                if common is None:common=public
                else:np.testing.assert_array_equal(common,public)
                for c,ids in enumerate(private):
                    np.testing.assert_array_equal(np.bincount(labels[ids],minlength=10),diag['client_class_histograms'][c])
                other=data.partition_indices(labels,16384,6,seed,partition)
                for a,b in zip([public,*private],[other[0],*other[1]]):np.testing.assert_array_equal(a,b)
                if partition=='iid':
                    old=core.split_indices(60000,16384,6,seed)
                    for a,b in zip(private,old[1]):np.testing.assert_array_equal(a,b)

    def test_missing_classes_and_transport_residual(self):
        labels=np.repeat([0,1,2],[120,60,20]).astype(np.int64)
        for partition in data.PARTITIONS:
            _,private,diag=data.partition_indices(labels,32,6,7,partition)
            self.assertLessEqual(max(map(len,private))-min(map(len,private)),1)
            self.assertTrue(all(set(range(3,10)).issubset(x) for x in diag['client_missing_classes']))
        with self.assertRaises(ValueError):data.partition_indices(labels,32,6,7,'unknown')

    def test_private_only_local_and_exact_bed_fixture(self):
        cfg=Config(dimensions=(6,9),public_pool=64,samples=16,classes=3,
            rounds=4,train_limit=104,test_limit=24,pretrain_epochs=1,
            prepare_threads=1,private_batch=7,public_edge_batch=3,eval_every=1)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root=Path(tmp);directory=fixture(root/'fixture',cfg)
            with threadpool_limits(limits=1):
                result=run(directory,cfg,fixture=True,progress=False)
                prepared=core.Prepared(directory,cfg,allow_test_fixture=True)
                try:
                    heads=[Head(d,cfg.classes,7,i) for i,d in enumerate(cfg.dimensions)]
                    for rnd in range(1,cfg.rounds+1):
                        for c,head in enumerate(heads):private_epoch(head,prepared.private[c],prepared.pseudo[c],cfg,7,c,rnd)
                finally:prepared.close()
            self.assertEqual(result['summary']['Local']['final_head_digest'],heads_digest(heads))
            self.assertEqual(result['validation']['mismatches'],0)
            self.assertTrue(all(r['public_optimizer_steps']==0 and not r['traffic'] and r['student_forward_endpoints']==0
                for r in result['round_records'] if r['method']=='Local'))
            result['partition']='fixture'
            reports(root,[result],[])
            self.assertTrue((root/'summary.json').exists())
            self.assertEqual(result['summary']['B']['final_head_digest'],result['summary']['D']['final_head_digest'])

    def test_preparation_adapter_cache_separation_and_corruption(self):
        cfg=Config(dimensions=(6,9),public_pool=64,samples=16,classes=3,
            rounds=3,train_limit=104,test_limit=24,pretrain_epochs=1,prepare_threads=1)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
            root=Path(tmp);idx=root/'idx';idx.mkdir();rng=np.random.default_rng(12)
            for prefix,count in [('train',104),('t10k',24)]:
                with gzip.open(idx/f'{prefix}-images-idx3-ubyte.gz','wb') as h:
                    h.write(struct.pack('>IIII',2051,count,28,28)+rng.integers(256,size=(count,784),dtype=np.uint8).tobytes())
                with gzip.open(idx/f'{prefix}-labels-idx1-ubyte.gz','wb') as h:
                    h.write(struct.pack('>II',2049,count)+(np.arange(count)%10).astype(np.uint8).tobytes())
            original_prepare=core.prepare;original_split=core.split_indices
            def development_prepare(*args,**kwargs):
                directory=original_prepare(*args,**kwargs)
                marker=directory/'prepared.json';metadata=json.loads(marker.read_text(encoding='utf-8'))
                metadata['dataset']='unit_test_fixture';marker.write_text(json.dumps(metadata),encoding='utf-8')
                return directory
            with patch.object(data,'ensure_data',return_value=idx),patch.object(core,'ensure_data',return_value=idx),patch.object(core,'prepare',side_effect=development_prepare):
                a=data.prepare(root/'cache',idx,cfg,7,'iid')
                self.assertIs(core.split_indices,original_split)
                b=data.prepare(root/'cache',idx,cfg,7,'dirichlet_0.1')
                self.assertIs(core.split_indices,original_split)
                self.assertNotEqual(a,b)
                data.verify(a,cfg,7,'iid');data.verify(b,cfg,7,'dirichlet_0.1')
                with self.assertRaises(ValueError):core.Prepared(a,cfg)
                with self.assertRaises(ValueError):data.verify(a,cfg,7,'dirichlet_0.1')
                (b/'client_0_pseudo.npy').write_bytes(b'broken')
                with self.assertRaises(ValueError):data.verify(b,cfg,7,'dirichlet_0.1')
            with patch.object(data,'ensure_data',return_value=idx),patch.object(core,'prepare',side_effect=RuntimeError('injected')):
                with self.assertRaises(RuntimeError):data.prepare(root/'failcache',idx,cfg,8,'dirichlet_0.5')
                self.assertIs(core.split_indices,original_split)


if __name__=='__main__':unittest.main()
