import copy,json,tempfile,unittest
from dataclasses import replace
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.config import Config
from experiments.public_scaling.data import Prepared,source_hashes
from experiments.public_scaling.engine import Method,heads_digest
from experiments.public_scaling.head import Head,private_epoch,public_epoch,relation_loss_grad
from experiments.public_scaling.test_scaling import fixture
from experiments.public_scaling.util import seal_payload
from .design import Spec,plan
from .student import selected_edges,update,Coverage
from .engine import BudgetMethod,run
from .run import check_reference
from .report import reports

class Tests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.cfg=Config(dimensions=(6,9),public_pool=64,samples=16,classes=3,rounds=4,
            train_limit=104,test_limit=24,pretrain_epochs=1,prepare_threads=1,
            private_batch=7,public_edge_batch=4,eval_every=2)
        self.directory=fixture(Path(self.temp.name)/'fixture',self.cfg)
    def tearDown(self):self.temp.cleanup()

    def test_formal_plan_has_one_anchor_and_fixed_budget(self):
        specs=plan('full','cuda')
        self.assertEqual([(s.config.samples,s.policy,s.effective_steps) for s in specs],[(4096,'full',8),(16384,'full',32),(16384,'fixed',8)])
        self.assertEqual(len({str(s.config.preparation()) for s in specs}),1)
        self.assertEqual(len({s.case_id for s in specs}),3)
        with self.assertRaises(ValueError):Spec(self.cfg,'fixed',3).validate()
        with self.assertRaises(ValueError):Spec(self.cfg,'full',2).validate()

    def test_full_student_and_anchor_equal_accepted_public_epoch(self):
        with threadpool_limits(limits=1):
            d=Prepared(self.directory,self.cfg,allow_test_fixture=True)
            try:
                targets=np.linspace(0,1,len(d.edges))
                for c,width in enumerate(self.cfg.dimensions):
                    a,b,z=[Head(width,self.cfg.classes,7,c) for _ in range(3)]
                    oldloss,oldpoints=public_epoch(a,d.public[c],d.edges,targets,self.cfg,7,c,1)
                    newloss,newpoints,ids=update(b,d.public[c],d.edges,targets,Spec(self.cfg),7,c,1)
                    update(z,d.public[c],d.edges,targets,Spec(self.cfg,'fixed',2),7,c,1)
                    np.testing.assert_array_equal(a.w,b.w);np.testing.assert_array_equal(a.b,b.b);np.testing.assert_array_equal(a.w,z.w)
                    self.assertEqual((oldloss,oldpoints),(newloss,newpoints));self.assertEqual(len(ids),len(d.edges))
            finally:d.close()

    def test_full_learning_matches_original_bed(self):
        with threadpool_limits(limits=1):
            d=Prepared(self.directory,self.cfg,allow_test_fixture=True)
            try:
                for name in ('B','E','D'):
                    old=Method(name,d,self.cfg);new=BudgetMethod(name,d,Spec(self.cfg))
                    for rnd in range(1,5):
                        a,ar,_=old.step(rnd);b,br,_,_=new.step(rnd)
                        self.assertEqual(a['head_digest_after_public'],b['head_digest_after_public']);self.assertEqual(a['traffic'],b['traffic'])
                        np.testing.assert_array_equal(ar,br)
            finally:d.close()

    def test_fixed_learning_against_independent_manual_sgd(self):
        cfg=replace(self.cfg,samples=64);spec=Spec(cfg,'fixed',2)
        with threadpool_limits(limits=1):
            d=Prepared(self.directory,cfg,allow_test_fixture=True)
            try:
                model=BudgetMethod('B',d,spec);heads=[Head(w,cfg.classes,7,c) for c,w in enumerate(cfg.dimensions)]
                for rnd in range(1,5):
                    for c,h in enumerate(heads):private_epoch(h,d.private[c],d.pseudo[c],cfg,7,c,rnd)
                    labels=[(z@h.w.T+h.b).argmax(axis=1) for z,h in zip(d.public,heads)]
                    rel=np.array([y[d.edges[:,0]]==y[d.edges[:,1]] for y in labels]);targets=rel.mean(axis=0)
                    for c,h in enumerate(heads):
                        ids=np.random.default_rng(np.random.SeedSequence([7,402,c,rnd,0])).permutation(len(d.edges))[:8]
                        for off in (0,4):
                            batch=ids[off:off+4];points,inverse=np.unique(d.edges[batch].ravel(),return_inverse=True)
                            _,dw,db=relation_loss_grad(d.public[c][points],inverse.reshape(-1,2),targets[batch],h.w,h.b)
                            h.apply(dw,db,cfg.head_lr*cfg.public_weight)
                    row,actual,*_=model.step(rnd)
                    np.testing.assert_array_equal(actual,rel);self.assertEqual(heads_digest(heads),row['head_digest_after_public'])
                    self.assertEqual(row['public_edges_consumed'],16);self.assertEqual(row['public_optimizer_steps'],4)
            finally:d.close()

    def test_fixed_oracle_is_full_graph_and_coverage_is_actual_union(self):
        cfg=replace(self.cfg,samples=64);spec=Spec(cfg,'fixed',2)
        with threadpool_limits(limits=1):r=run(self.directory,spec,fixture=True,progress=False)
        n=len(cfg.dimensions);e=32
        self.assertEqual(r['validation']['relation_comparisons'],3*cfg.rounds*n*e)
        self.assertEqual(r['validation']['candidate_membership_comparisons'],2*cfg.rounds*n*cfg.samples)
        self.assertEqual(r['validation']['mismatches'],0)
        with threadpool_limits(limits=1):d=Prepared(self.directory,cfg,allow_test_fixture=True)
        try:
            seen=[set() for _ in range(n)];points=[set() for _ in range(n)]
            for rnd in range(1,5):
                for c in range(n):
                    ids=np.random.default_rng(np.random.SeedSequence([7,402,c,rnd,0])).permutation(e)[:8]
                    seen[c].update(ids.tolist());points[c].update(d.edges[ids].ravel().tolist())
                obs=r['coverage_records'][rnd-1]
                self.assertEqual(obs['mean_client_edge_fraction'],sum(map(len,seen))/(n*e))
                self.assertEqual(obs['mean_client_endpoint_fraction'],sum(map(len,points))/(n*cfg.samples))
            self.assertEqual(r['coverage'],{k:v for k,v in r['coverage_records'][-1].items() if k!='round'})
            rows=r['round_records']
            for rnd in range(1,5):self.assertEqual(len({x['head_digest_after_public'] for x in rows if x['round']==rnd}),1)
        finally:d.close()

    def test_single_method_replays_match_paired_final_heads(self):
        spec=Spec(replace(self.cfg,samples=64),'fixed',2)
        with threadpool_limits(limits=1):
            paired=run(self.directory,spec,fixture=True,progress=False)
            for name in ('B','E','D'):
                one=run(self.directory,spec,names=(name,),validate=False,metrics=False,fixture=True,progress=False)
                self.assertEqual(one['summary'][name]['final_head_digest'],paired['summary'][name]['final_head_digest'])
                self.assertEqual(one['summary'][name]['persistent_method_array_bytes'],paired['summary'][name]['persistent_method_array_bytes'])

    def test_reference_rejects_resealed_duplicate(self):
        with threadpool_limits(limits=1):result=run(self.directory,Spec(self.cfg),fixture=True,progress=False)
        result['partition']='fixture'
        ref=dict(result,identity=dict(core_source_hashes=source_hashes()))
        self.assertTrue(check_reference(result,seal_payload(ref))['checked'])
        bad=copy.deepcopy(ref);bad['round_records'][-1]=copy.deepcopy(bad['round_records'][0])
        with self.assertRaises(ValueError):check_reference(result,seal_payload(bad))

    def test_report_cost_pairing_and_permitted_quality_drop(self):
        import csv
        cfg=replace(self.cfg,samples=64)
        def case(policy):
            spec=Spec(cfg) if policy=='full' else Spec(cfg,'fixed',2)
            accs=[0.3,0.8] if policy=='full' else [0.49,0.59]
            heads=[10.,8.,7.] if policy=='full' else [6.,5.,4.]
            summaries={}
            for m,t in zip(('B','E','D'),heads):
                metric=dict(method=m,round=cfg.rounds,mean=dict(acc=sum(accs)/2,nmi=.5,ari=.5),clients=[dict(client=c,width=cfg.dimensions[c],acc=a,nmi=.5,ari=.5) for c,a in enumerate(accs)])
                summaries[m]=dict(head_pipeline_seconds=t,with_shared_preparation_seconds=t+20,initialization_seconds=.01,private_seconds=1.,generation_seconds=1.,exchange_seconds=.1,public_seconds=1.,
                    teacher_recompute_fraction=.1,generation_fraction=1/t,persistent_method_array_bytes=100,traffic=dict(total_bytes=1000),final_metrics=metric,final_head_digest='hand_fixture',public_optimizer_steps=spec.effective_steps*2*cfg.rounds,student_forward_endpoints=64)
            return dict(partition='iid',seed=7,spec=spec.json(),config=cfg.json(),case_id=spec.case_id,summary=summaries,coverage={},metrics=[])
        out=Path(self.temp.name)/'report';full,fixed=case('full'),case('fixed')
        def read_csv(name):return list(csv.DictReader((out/name).read_text(encoding='utf-8').splitlines()))
        reports(out,[fixed],[])
        rows=read_csv('quality_guardrails.csv')
        self.assertEqual(rows[0]['within_acc_guardrail'],'pending')
        reports(out,[full,fixed],[])
        rows=read_csv('quality_guardrails.csv')
        self.assertEqual(rows[0]['within_acc_guardrail'],'True')
        self.assertAlmostEqual(float(rows[0]['worst_client_acc_delta']),.19)
        self.assertAlmostEqual(float(rows[0]['min_same_client_acc_delta']),-.21)
        costs=read_csv('paired_cost.csv')
        row=next(r for r in costs if r['case_id']=='m64_fixed2' and r['comparison']=='D_over_B' and r['measure']=='head_pipeline_seconds')
        self.assertAlmostEqual(float(row['ratio_D_over_reference']),4/6)
        self.assertAlmostEqual(float(row['seconds_saved_reference_minus_D']),2.)
        self.assertEqual(len(read_csv('budget_effects.csv')),3)

if __name__=='__main__':unittest.main()
