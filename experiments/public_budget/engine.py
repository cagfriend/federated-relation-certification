"""Original certificate/protocol/private SGD; only public edge traversal changes."""
from time import perf_counter
import hashlib
import numpy as np
from threadpoolctl import threadpool_info
from experiments.public_scaling.data import Prepared
from experiments.public_scaling.engine import Method,audit,evaluate,heads_digest,METHODS as MODES
from experiments.public_scaling.head import private_epoch
from experiments.public_scaling.certification import RelationGenerator
from .design import METHODS
from .student import update,schedule_digest,Coverage

class BudgetMethod(Method):
    def __init__(self,name,data,spec):
        super().__init__(name,data,spec.config);self.spec=spec

    def step(self,rnd):
        start=perf_counter();losses=[];private_points=0
        for c,h in enumerate(self.heads):
            loss,n=private_epoch(h,self.data.private[c],self.data.pseudo[c],self.config,self.data.seed,c,rnd)
            losses.append(loss);private_points+=n
        private_s=perf_counter()-start
        stage=perf_counter();relations=[];snapshots=[];statistics=[]
        for c,h in enumerate(self.heads):
            w,b=h.w.copy(),h.b.copy();snapshots.append((w,b))
            if rnd==1:
                g=RelationGenerator(self.data.public[c],w,b,self.data.edges,MODES[self.name]);self.generators.append(g)
                relations.append(g.initial_relations);del g.initial_relations
                statistics.append(dict(forward_endpoints=self.config.samples,certified_edges_before_refresh=0,candidate_entries=self.config.samples*self.config.classes))
            else:
                rel,stat=self.generators[c].generate(w,b);relations.append(rel);statistics.append(stat)
        generation_s=perf_counter()-stage;stage=perf_counter()
        # Always aggregate the complete graph, including edges the student skips.
        traffic=self.protocol.exchange(relations)
        targets=[counts.astype(np.float64)/len(self.heads) for counts in self.protocol.client_counts]
        exchange_s=perf_counter()-stage;stage=perf_counter();public_losses=[];public_points=0;orders=[]
        for c,h in enumerate(self.heads):
            loss,n,order=update(h,self.data.public[c],self.data.edges,targets[c],self.spec,self.data.seed,c,rnd)
            public_losses.append(loss);public_points+=n;orders.append(order)
        public_s=perf_counter()-stage;total=perf_counter()-start
        # Previous generator snapshots deliberately remain the last TEACHER.
        # The next movement includes prior public SGD plus current private SGD.
        row=dict(method=self.name,round=rnd,private_seconds=private_s,generation_seconds=generation_s,
            exchange_seconds=exchange_s,public_seconds=public_s,pipeline_seconds=total,
            private_loss=float(np.mean(losses)),public_loss=float(np.mean(public_losses)),
            private_forward_endpoints=private_points,student_forward_endpoints=public_points,
            private_optimizer_steps=sum((len(z)+self.config.private_batch-1)//self.config.private_batch for z in self.data.private)*self.config.private_epochs,
            public_optimizer_steps=self.spec.effective_steps*len(self.heads),
            public_edges_consumed=sum(map(len,orders)),public_schedule_digest=schedule_digest(orders),
            positive_relation_fraction=float(np.mean(relations)),
            committed_counts_digest=hashlib.sha256(self.protocol.counts.astype('<u8').tobytes()).hexdigest(),
            received_counts_digests=[hashlib.sha256(v.astype('<u8').tobytes()).hexdigest() for v in self.protocol.client_counts],
            teacher_forward_endpoints=sum(s['forward_endpoints'] for s in statistics),
            certified_edges_before_refresh=sum(s['certified_edges_before_refresh'] for s in statistics),
            client_statistics=statistics,traffic=traffic,head_digest_after_public=heads_digest(self.heads),
            persistent_method_array_bytes=self.persistent_bytes())
        return row,relations,snapshots,orders

def run(directory,spec,*,names=METHODS,validate=True,metrics=True,progress=True,fixture=False):
    spec.validate();cfg=spec.config
    if not names or len(set(names))!=len(names) or any(n not in METHODS for n in names):raise ValueError('Invalid methods')
    if any(p['num_threads']!=cfg.threads for p in threadpool_info() if p['user_api']=='blas'):raise ValueError('Unexpected BLAS threads')
    t=perf_counter();data=Prepared(directory,cfg,allow_test_fixture=fixture);load=perf_counter()-t
    try:
        shift=data.seed%len(names);methods={n:BudgetMethod(n,data,spec) for n in names[shift:]+names[:shift]}
        initial={heads_digest(m.heads) for m in methods.values()}
        if len(initial)!=1:raise AssertionError('Initial heads differ')
        observer=Coverage(len(cfg.dimensions),data.edges,cfg.samples) if validate else None
        rr=[];quality=[];coverage_rows=[];checks=members=0;audit_s=eval_s=0.
        for rnd in range(1,cfg.rounds+1):
            outputs={};rows={};shift=(data.seed+rnd)%len(names)
            for n in names[shift:]+names[:shift]:
                row,relations,snapshots,orders=methods[n].step(rnd)
                rr.append(row);rows[n]=row;outputs[n]=(relations,snapshots,orders)
            if validate:
                t=perf_counter()
                for key in ('head_digest_after_public','public_schedule_digest','public_optimizer_steps','student_forward_endpoints','public_edges_consumed','committed_counts_digest','private_loss','public_loss'):
                    if len({rows[n][key] for n in names})!=1:raise AssertionError('B/E/D budget or trajectory differs: '+key)
                if any(rows[n]['traffic']!=rows[names[0]]['traffic'] for n in names):raise AssertionError('B/E/D traffic differs')
                if any(any(h!=rows[n]['committed_counts_digest'] for h in rows[n]['received_counts_digests']) for n in names):raise AssertionError('Student target digests differ')
                for n in names:
                    a,b=audit(methods[n],*outputs[n][:2],data);checks+=a;members+=b
                coverage_rows.append(dict(round=rnd,**observer.observe(outputs[names[0]][2])))
                audit_s+=perf_counter()-t
            if metrics and (rnd%cfg.eval_every==0 or rnd==cfg.rounds):
                t=perf_counter();evaluations=[]
                for n in names:
                    q=dict(round=rnd,method=n,**evaluate(methods[n].heads,data,cfg));quality.append(q);evaluations.append(q)
                if validate and any(q['clients']!=evaluations[0]['clients'] for q in evaluations):raise AssertionError('B/E/D evaluations differ')
                eval_s+=perf_counter()-t
            if progress and (rnd%10==0 or rnd==cfg.rounds):print(f'  {spec.case_id} seed={data.seed}: {rnd}/{cfg.rounds}',flush=True)
        summary={}
        for n,m in methods.items():
            rows=[r for r in rr if r['method']==n];pipeline=m.initialization_seconds+sum(r['pipeline_seconds'] for r in rows)
            gen=sum(r['generation_seconds'] for r in rows)
            summary[n]=dict(initialization_seconds=m.initialization_seconds,head_pipeline_seconds=pipeline,
                with_shared_preparation_seconds=data.metadata['preparation_wall_seconds_excluding_download']+load+pipeline,
                **{p+'_seconds':sum(r[p+'_seconds'] for r in rows) for p in ('private','generation','exchange','public')},
                generation_fraction=gen/pipeline,teacher_recompute_fraction=None if cfg.rounds==1 else sum(r['teacher_forward_endpoints'] for r in rows[1:])/(cfg.samples*len(cfg.dimensions)*(cfg.rounds-1)),
                persistent_method_array_bytes=m.persistent_bytes(),initial_traffic=m.initial_traffic,traffic=m.protocol.traffic.snapshot(),
                public_optimizer_steps=sum(r['public_optimizer_steps'] for r in rows),student_forward_endpoints=sum(r['student_forward_endpoints'] for r in rows),
                final_head_digest=heads_digest(m.heads),final_metrics=next((q for q in reversed(quality) if q['method']==n),None))
        return dict(seed=data.seed,dataset=data.metadata['dataset'],config=cfg.json(),spec=spec.json(),case_id=spec.case_id,
            initial_head_digest=next(iter(initial)),graph_sha256=hashlib.sha256(data.edges.astype('<u4').tobytes()).hexdigest(),
            prepared_directory=str(data.directory.resolve()),common_preparation_seconds=data.metadata['preparation_wall_seconds_excluding_download'],shared_loading_seconds=load,
            summary=summary,round_records=rr,metrics=quality,coverage=observer.snapshot() if observer else None,coverage_records=coverage_rows,
            validation=dict(enabled=validate,mismatches=0 if validate else None,relation_comparisons=checks,candidate_membership_comparisons=members,
                audit_and_coverage_seconds_excluded=audit_s,evaluation_seconds_excluded=eval_s))
    finally:data.close()
