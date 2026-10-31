import copy,tempfile,unittest
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.config import Config
from experiments.public_scaling.data import Prepared
from experiments.public_scaling.test_scaling import fixture
from experiments.public_scaling.engine import Method,heads_digest
from experiments.public_scaling.head import Head,private_epoch
from .engine import Branch,run
from .targets import target_matrix,relation_record,validate_record,permutation,NAMES,digest
from .diagnostics import alignment
from .run import check_reference
from .report import reports
from experiments.public_scaling.util import seal_payload
from experiments.public_scaling.data import source_hashes

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.cfg=Config(dimensions=(6,9),public_pool=64,samples=16,classes=3,rounds=4,
            train_limit=104,test_limit=24,pretrain_epochs=1,prepare_threads=1,
            private_batch=7,public_edge_batch=3,eval_every=2)
        self.directory=fixture(Path(self.temp.name)/'fixture',self.cfg)
    def tearDown(self):self.temp.cleanup()

    def test_targets_preserve_values_and_replay(self):
        r=np.array([[1,0,0,0,1,1,1,0],[0,1,0,0,1,0,1,0],[0,1,0,1,1,0,0,0]],dtype=np.uint8)
        np.testing.assert_array_equal(target_matrix(r,'Self',7,3),r)
        avg=np.broadcast_to(r.mean(axis=0),r.shape)
        np.testing.assert_array_equal(target_matrix(r,'Aggregate',7,3),avg)
        sh=target_matrix(r,'Shuffled',7,3)
        for row in sh:np.testing.assert_array_equal(np.sort(row),np.sort(avg[0]))
        np.testing.assert_array_equal(sh,avg[:,permutation(8,7,3)])
        for kind in ('Self','Aggregate','Shuffled'):
            rec=relation_record(r,kind,7,3,np.array([1,0,1,0,1,0,1,0]))
            np.testing.assert_array_equal(validate_record(rec,7),target_matrix(r,kind,7,3))
            bad=copy.deepcopy(rec);bad['applied_targets_digest']='x'
            with self.assertRaises(ValueError):validate_record(bad,7)
        const=relation_record(np.zeros((3,8),dtype=np.uint8),'Shuffled',7,3)
        self.assertEqual(const['shuffled_changed_edge_fraction'],0.)
        with self.assertRaises(ValueError):target_matrix(r,'bad',7,3)

    def test_aggregate_exactly_reuses_old_learning_semantics(self):
        with threadpool_limits(limits=1):
            d=Prepared(self.directory,self.cfg,allow_test_fixture=True)
            try:
                new=Branch('Aggregate',d,self.cfg);old=Method('B',d,self.cfg)
                local=Branch('Local',d,self.cfg);manual=[Head(w,self.cfg.classes,7,c) for c,w in enumerate(self.cfg.dimensions)]
                for rnd in range(1,self.cfg.rounds+1):
                    row,snap,rel,record=new.step(rnd,True,None);oldrow,oldrel,_=old.step(rnd)
                    self.assertEqual(heads_digest(new.heads),heads_digest(old.heads))
                    np.testing.assert_array_equal(rel,np.array(oldrel))
                    self.assertEqual(row['traffic'],oldrow['traffic'])
                    self.assertEqual(new.protocol.traffic.snapshot(),old.protocol.traffic.snapshot())
                    self.assertEqual(row['head_digest_before_public'],digest(*[a for pair in snap for a in pair]))
                    lrow,*_=local.step(rnd,False,None)
                    for c,h in enumerate(manual):private_epoch(h,d.private[c],d.pseudo[c],self.cfg,7,c,rnd)
                    self.assertEqual(heads_digest(local.heads),heads_digest(manual))
                    self.assertEqual(lrow['public_optimizer_steps'],0)
            finally:d.close()

    def test_probes_do_not_change_training_and_labels_are_offline_only(self):
        with threadpool_limits(limits=1):
            np.random.seed(123);state=np.random.get_state()
            a=run(self.directory,self.cfg,public_truth=np.arange(self.cfg.samples)%3,probes=True,progress=False,fixture=True)
            b=run(self.directory,self.cfg,public_truth=np.zeros(self.cfg.samples,dtype=int),probes=False,progress=False,fixture=True)
            after=np.random.get_state()
        self.assertEqual(state[0],after[0]);np.testing.assert_array_equal(state[1],after[1]);self.assertEqual(state[2:],after[2:])
        for method in NAMES:
            self.assertEqual(a['summary'][method]['final_head_digest'],b['summary'][method]['final_head_digest'])
            self.assertEqual(a['summary'][method]['traffic'],b['summary'][method]['traffic'])
        self.assertEqual([r['head_digest_after_public'] for r in a['round_records']],[r['head_digest_after_public'] for r in b['round_records']])
        self.assertEqual(len(a['diagnostics']),3*4*len(self.cfg.dimensions)*3)
        groups={}
        for r in a['diagnostics']:groups.setdefault((r['round'],r['anchor'],r['client']),[]).append(r)
        for rows in groups.values():
            for key in ('private_grad_norm','private_loss','student_snapshot_digest','private_batch_digest','public_edge_batch_digest'):
                self.assertEqual(len({r[key] for r in rows}),1)
        rows=a['round_records']
        for rnd in range(1,self.cfg.rounds+1):
            public=[r for r in rows if r['round']==rnd and r['method']!='Local']
            self.assertEqual(len({r['public_optimizer_steps'] for r in public}),1)
            self.assertEqual(len({r['student_forward_endpoints'] for r in public}),1)

    def test_gradient_zero_and_opposed_vectors(self):
        zero=(np.zeros((2,2)),np.zeros(2));g=(np.array([[1.,2.],[3.,4.]]),np.array([5.,6.]))
        r=alignment(zero,g,2.)
        self.assertIsNone(r['gradient_cosine']);self.assertIsNone(r['gradient_angle_degrees']);self.assertIsNone(r['weighted_public_private_norm_ratio'])
        r=alignment(g,tuple(-x for x in g),2.)
        self.assertAlmostEqual(r['gradient_cosine'],-1.);self.assertAlmostEqual(r['gradient_angle_degrees'],180.)
        self.assertAlmostEqual(r['weighted_public_private_norm_ratio'],2.)

    def test_reference_rejects_resealed_duplicate_and_changed_metrics(self):
        # Hand-constructed protocol records, not a claim to have trained official data.
        cfg=dict(rounds=2,eval_every=1)
        rows=[dict(round=r,method=m,head_digest_after_public=f'{m}_{r}',traffic={}) for r in (1,2) for m in ('Local','Aggregate')]
        metrics=[dict(round=r,method=m,clients=[dict(client=0,acc=0.5,nmi=0.3,ari=0.2)],mean=dict(acc=0.5,nmi=0.3,ari=0.2)) for r in (1,2) for m in ('Local','Aggregate')]
        case=dict(config=cfg,seed=7,partition='iid',prepared_directory='unit_fixture',initial_head_digest='fixture',
            round_records=rows,metrics=metrics,summary={m:dict(traffic={}) for m in ('Local','Aggregate')})
        reference=dict(case,dataset='Fashion-MNIST',identity=dict(core_source_hashes=source_hashes()),
            round_records=[dict(r,method='B' if r['method']=='Aggregate' else 'Local') for r in rows],
            metrics=[dict(m,method='B' if m['method']=='Aggregate' else 'Local') for m in metrics],
            summary=dict(Local=dict(traffic={}),B=dict(traffic={})))
        self.assertTrue(check_reference(case,seal_payload(reference))['checked'])
        for field in ('round_records','metrics'):
            bad=copy.deepcopy(reference);bad[field][-1]=copy.deepcopy(bad[field][0])
            with self.assertRaises(ValueError):check_reference(case,seal_payload(bad))
        bad=copy.deepcopy(reference);bad['metrics'][0]['mean']['acc']=0.6
        with self.assertRaises(ValueError):check_reference(case,seal_payload(bad))

    def test_joint_gate_and_smoke_never_make_research_claim(self):
        def cases(preset,shuffled):
            result=[]
            for seed in (404,505,606):
                summary={};metrics=[]
                for method,acc in [('Local',0.4),('Self',0.4),('Aggregate',0.42),('Shuffled',shuffled)]:
                    metric=dict(round=200,method=method,mean=dict(acc=acc,nmi=acc,ari=acc),clients=[dict(client=0,width=6,acc=acc,nmi=acc,ari=acc)])
                    metrics.append(metric);summary[method]=dict(final_metrics=metric)
                result.append(dict(seed=seed,partition='dirichlet_0.1',identity=dict(preset=preset),config={},metrics=metrics,summary=summary,diagnostics=[],target_records=[]))
            return result
        import json
        out=Path(self.temp.name)/'report'
        reports(out,cases('full',0.419))
        data=json.loads((out/'summary.json').read_text(encoding='utf-8'))
        primary=[r for r in data['paired_quality'] if r['row_type']=='across_seed_summary' and r['comparison'] in ('Aggregate-Self','Aggregate-Shuffled')]
        self.assertEqual({r['screening_status'] for r in primary},{'探索筛查门槛未达到'})
        reports(out,cases('full',0.4))
        self.assertIn('探索筛查门槛达到，仍需新seed确认',(out/'report.md').read_text(encoding='utf-8'))
        reports(out,cases('smoke',0.2))
        data=json.loads((out/'summary.json').read_text(encoding='utf-8'))
        primary=[r for r in data['paired_quality'] if r['row_type']=='across_seed_summary' and r['comparison'] in ('Aggregate-Self','Aggregate-Shuffled')]
        self.assertEqual({r['screening_status'] for r in primary},{'smoke仅路径验证，不作门槛判定'})

if __name__=='__main__':unittest.main()
