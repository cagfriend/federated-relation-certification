from dataclasses import replace
import gc
import gzip
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from threadpoolctl import threadpool_limits

from .config import Config, make_plan, preset
from .data import Prepared, prepare, preparation_key, sha, split_indices, verify_prepared
from .engine import Method, audit, run_seed
from .graphs import make_graph
from .head import ce_loss_grad, relation_loss_grad
from .run import check_shared_cases, main, memory_configs
from .util import seal_payload, validate_payload


def fixture(directory, config, seed=7):
    """Synthetic feature fixture, never valid as a real Fashion-MNIST run."""
    directory.mkdir()
    rng = np.random.default_rng(seed)
    public, private = split_indices(config.train_limit, config.public_pool, len(config.dimensions), seed)
    np.save(directory / 'public_ids.npy', public)
    np.save(directory / 'test_labels.npy', np.arange(config.test_limit) % config.classes)
    for i, width in enumerate(config.dimensions):
        np.save(directory / f'client_{i}_private_ids.npy', private[i])
        for name, count in [('private', len(private[i])), ('public', config.public_pool), ('test', config.test_limit)]:
            z = rng.normal(size=(count, width)).astype(np.float32)
            z /= np.linalg.norm(z, axis=1, keepdims=True)
            np.save(directory / f'client_{i}_{name}.npy', z)
        np.save(directory / f'client_{i}_pseudo.npy', rng.integers(config.classes, size=len(private[i])))
    metadata = {'dataset': 'unit_test_fixture', 'seed': seed, 'config': config.preparation(),
                'preparation_wall_seconds_excluding_download': 1.0,
                'files': {p.name: sha(p) for p in directory.iterdir()}}
    (directory / 'prepared.json').write_text(json.dumps(metadata), encoding='utf-8')
    return directory


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.root = Path(self.temp.name)
        self.config = Config(dimensions=(6, 9), public_pool=64, samples=16, classes=3,
                             rounds=3, train_limit=104, test_limit=24, pretrain_epochs=1,
                             prepare_threads=1, private_batch=7, public_edge_batch=3, eval_every=1)

    def tearDown(self):
        gc.collect()
        self.temp.cleanup()

    def test_full_design_counts_and_fixed_preparation(self):
        plan = make_plan(preset('full'), 'all')
        self.assertEqual([(c.samples, c.degree) for c in plan], [(4096,1),(8192,1),(16384,1),(4096,4),(4096,8)])
        self.assertEqual(len(plan) * 3 * 3, 45)
        self.assertTrue(all(c.preparation() == plan[0].preparation() for c in plan))
        self.assertEqual([c.case_id for c in memory_configs(plan, 'largest')], ['m16384_d1', 'm4096_d8'])

    def test_fixed_split_and_public_prefix_coverage(self):
        public, private = split_indices(60000, 16384, 6, 404)
        self.assertEqual(list(map(len, private)), [7270,7270,7269,7269,7269,7269])
        np.testing.assert_array_equal(np.sort(np.concatenate([public] + private)), np.arange(60000))
        for m in (4096,8192,16384):
            self.assertFalse(np.isin(public[:m], np.concatenate(private)).any())

    def test_nested_regular_graphs_and_prefix_matching(self):
        for m in (16,32,64):
            previous = set()
            for degree in (1,4,8):
                edges = make_graph(m, degree, 404)
                edge_set = set(map(tuple, edges))
                self.assertTrue(previous <= edge_set)
                self.assertEqual(len(edge_set), m * degree // 2)
                self.assertTrue(np.all(edges[:,0] < edges[:,1]))
                np.testing.assert_array_equal(np.bincount(edges.ravel(), minlength=m), np.full(m,degree))
                previous = edge_set
        a = set(map(tuple, make_graph(16,1,404)))
        b = set(map(tuple, make_graph(64,1,404)))
        self.assertTrue(a <= b)

    def gradient(self, function):
        rng = np.random.default_rng(1)
        x,w,b = rng.normal(size=(5,4)),rng.normal(size=(3,4)),rng.normal(size=3)
        _,dw,db = function(x,w,b)
        for param,analytic in ((w,dw),(b,db)):
            numeric=np.zeros_like(param)
            for idx in np.ndindex(param.shape):
                old=param[idx]
                param[idx]=old+1e-6
                high=function(x,w,b)[0]
                param[idx]=old-1e-6
                low=function(x,w,b)[0]
                param[idx]=old
                numeric[idx]=(high-low)/2e-6
            np.testing.assert_allclose(analytic,numeric,rtol=2e-5,atol=1e-7)

    def test_private_ce_gradient(self):
        self.gradient(lambda x,w,b:ce_loss_grad(x,np.array([0,1,2,0,1]),w,b))

    def test_public_gradient_repeated_and_self_endpoints(self):
        self.gradient(lambda x,w,b:relation_loss_grad(x,np.array([[0,1],[0,2],[2,3],[4,4]]),np.array([0.,.3,1.,.7]),w,b))

    def test_fixture_is_not_real_data(self):
        path=fixture(self.root/'features',self.config)
        with self.assertRaises(ValueError):
            Prepared(path,self.config)

    def test_sparse_dense_and_larger_public_sgd_trajectories(self):
        path=fixture(self.root/'features',self.config)
        cases=[]
        for c in make_plan(self.config,'all'):
            with threadpool_limits(limits=1):
                result=run_seed(path,c,progress=False,allow_test_fixture=True)
            cases.append(result)
            self.assertEqual(result['validation']['relation_comparisons'],3*c.rounds*2*(c.samples*c.degree//2))
            self.assertEqual(result['validation']['candidate_membership_comparisons'],2*c.rounds*2*c.samples)
            for t in range(1,c.rounds+1):
                rows=[r for r in result['round_records'] if r['round']==t]
                self.assertEqual(len({r['head_digest_after_public'] for r in rows}),1)
                self.assertTrue(all(r['traffic']==rows[0]['traffic'] for r in rows))
                expected=((c.samples*c.degree//2+c.public_edge_batch-1)//c.public_edge_batch)*2
                self.assertTrue(all(r['public_optimizer_steps']==expected for r in rows))
                self.assertTrue(all(r['private_optimizer_steps']==6 for r in rows))
        check_shared_cases(cases)
        self.assertEqual(len({c['prepared_directory'] for c in cases}),1)
        from .report import write_reports
        output=self.root/'reports'
        write_reports(output,cases,[])
        summary=json.loads((output/'paired_summary.json').read_text())
        self.assertEqual(summary['case_count'],5)
        self.assertEqual(summary['seed_count'],1)
        for c in cases:
            ratio=c['summary']['D']['training_pipeline_seconds']/c['summary']['B']['training_pipeline_seconds']
            self.assertEqual(summary['paired'][c['case_id']]['paired']['D_over_B']['training_pipeline_seconds']['median_ratio_D_over_reference'],ratio)

    def test_previous_public_update_is_in_next_certificate_delta(self):
        path=fixture(self.root/'features',self.config)
        data=Prepared(path,self.config,allow_test_fixture=True)
        method=Method('D',data,self.config)
        with patch('experiments.public_scaling.engine.private_epoch',return_value=(0.,0)):
            _,_,first=method.step(1)
            np.testing.assert_array_equal(method.generators[0].previous_weights,first[0][0])
            _,relations,second=method.step(2)
        delta=second[0][0]-first[0][0]
        expected=np.linalg.norm(delta[:,None,:]-delta[None,:,:],axis=2)
        self.assertGreater(expected.max(),0)
        np.testing.assert_allclose(method.generators[0].weight_prefix,expected)
        audit(method,relations,second,data)
        data.close()

    def test_pool_preparation_reused_across_cases_and_frozen(self):
        data_dir=self.root/'idx'
        data_dir.mkdir()
        rng=np.random.default_rng(12)
        for prefix,count in [('train',104),('t10k',24)]:
            with gzip.open(data_dir/f'{prefix}-images-idx3-ubyte.gz','wb') as handle:
                handle.write(struct.pack('>IIII',2051,count,28,28)+rng.integers(256,size=(count,784),dtype=np.uint8).tobytes())
        with gzip.open(data_dir/'t10k-labels-idx1-ubyte.gz','wb') as handle:
            handle.write(struct.pack('>II',2049,24)+(np.arange(24)%3).astype(np.uint8).tobytes())
        with patch('experiments.public_scaling.data.ensure_data',return_value=data_dir):
            path=prepare(self.root/'cache',data_dir,self.config,9)
            other=replace(self.config,samples=64,degree=4)
            self.assertEqual(prepare(self.root/'cache',data_dir,other,9),path)
        metadata=json.loads((path/'prepared.json').read_text())
        self.assertTrue(all(c['encoder_frozen'] for c in metadata['clients']))
        self.assertFalse((data_dir/'train-labels-idx1-ubyte.gz').exists())
        self.assertEqual(np.load(path/'client_0_public.npy').shape,(64,6))
        # Never allow generated IDX development fixtures to be mistaken for real results.
        metadata['dataset']='unit_test_fixture'
        (path/'prepared.json').write_text(json.dumps(metadata),encoding='utf-8')
        a=Prepared(path,self.config,allow_test_fixture=True)
        b=Prepared(path,other,allow_test_fixture=True)
        np.testing.assert_array_equal(a.public[0],b.public[0][:16])
        np.testing.assert_array_equal(a.private[0],b.private[0])
        a.close();b.close()

    def test_preparation_key_changes_only_for_preparation_policy(self):
        self.assertEqual(preparation_key(self.config,7),preparation_key(replace(self.config,samples=64,degree=8,rounds=7),7))
        self.assertNotEqual(preparation_key(self.config,7),preparation_key(replace(self.config,public_pool=96,train_limit=136),7))

    def test_corruption_and_payload_mutation_rejected(self):
        f=self.root/'array.npy'
        f.write_bytes(b'original')
        metadata={'files':{'array.npy':sha(f)}}
        f.write_bytes(b'changed')
        with self.assertRaises(ValueError):verify_prepared(self.root,metadata)
        obj=seal_payload({'seed':404,'seconds':1.23})
        validate_payload(obj)
        obj['seconds']=.01
        with self.assertRaises(ValueError):validate_payload(obj)

    def test_existing_output_not_overwritten(self):
        output=self.root/'existing'
        output.mkdir()
        sentinel=output/'old.json'
        sentinel.write_text('preserve')
        with patch('sys.argv',['run','--output',str(output)]):
            with self.assertRaises(FileExistsError):main()
        self.assertEqual(sentinel.read_text(),'preserve')

    def test_invalid_config_and_duplicate_report_pair(self):
        for c in [replace(self.config,degree=16),replace(self.config,classes=65),replace(self.config,samples=65),replace(self.config,public_pool=63)]:
            with self.assertRaises(ValueError):c.validate()
        from .report import write_reports
        duplicate={'case_id':'x','seed':1,'summary':{}}
        with self.assertRaises(ValueError):write_reports(self.root/'duplicates',[duplicate,duplicate],[])


if __name__=='__main__':
    unittest.main()
