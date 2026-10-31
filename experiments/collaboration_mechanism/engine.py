"""Four actual SGD branches; only public targets change between public branches."""
from time import perf_counter
import numpy as np
from threadpoolctl import threadpool_info
from experiments.public_scaling.data import Prepared
from experiments.public_scaling.head import Head,private_epoch,public_epoch
from experiments.public_scaling.engine import evaluate,heads_digest
from experiments.public_scaling.certification import hard_relations
from experiments.public_scaling.protocol import RelationProtocol
from .targets import NAMES,target_matrix,relation_record,validate_record,digest
from .diagnostics import probe

class Branch:
    def __init__(self,name,data,config):
        start=perf_counter();self.name=name;self.data=data;self.config=config
        self.heads=[Head(d,config.classes,data.seed,i) for i,d in enumerate(config.dimensions)]
        self.protocol=None if name in ('Local','Self') else RelationProtocol(data.edges,config.samples,config.classes,config.dimensions,adaptive=True)
        self.initial_traffic={} if self.protocol is None else self.protocol.traffic.snapshot()
        self.initialization_seconds=perf_counter()-start

    def step(self,rnd,checkpoint,truth):
        data=self.data;cfg=self.config;t=perf_counter();loss=[];private_points=0
        for c,head in enumerate(self.heads):
            v,k=private_epoch(head,data.private[c],data.pseudo[c],cfg,data.seed,c,rnd);loss.append(v);private_points+=k
        private_s=perf_counter()-t
        generation=exchange=public=0.;public_points=0;public_loss=None;traffic={};snapshots=None;relations=None;record=None
        pre_public=heads_digest(self.heads)
        if self.name!='Local':
            t=perf_counter();snapshots=[(h.w.copy(),h.b.copy()) for h in self.heads]
            labels=[(z@w.T+b).argmax(axis=1) for z,(w,b) in zip(data.public,snapshots)]
            relations=np.array([hard_relations(y,data.edges) for y in labels],dtype=np.uint8)
            generation=perf_counter()-t;t=perf_counter()
            if self.protocol is not None:
                traffic=self.protocol.exchange(list(relations))
                counts=relations.sum(axis=0,dtype=np.int64)
                if not np.array_equal(self.protocol.counts,counts) or any(not np.array_equal(v,counts) for v in self.protocol.client_counts):
                    raise AssertionError('Received targets do not match exact aggregate')
                if any(not np.array_equal(a,b) for a,b in zip(self.protocol.server_relations,relations)):raise AssertionError('Protocol changed relations')
            targets=target_matrix(relations,self.name,data.seed,rnd)
            exchange=perf_counter()-t;t=perf_counter();pl=[]
            for c,head in enumerate(self.heads):
                v,k=public_epoch(head,data.public[c],data.edges,targets[c],cfg,data.seed,c,rnd);pl.append(v);public_points+=k
            public_loss=float(np.mean(pl));public=perf_counter()-t
            # Read-only diagnostics and checks are outside phase timing.
            record=relation_record(relations,self.name,data.seed,rnd,truth)
            np.testing.assert_array_equal(validate_record(record,data.seed,truth),targets)
        elif checkpoint:
            # Local has no teacher work during training; this belongs to excluded probing.
            snapshots=[(h.w.copy(),h.b.copy()) for h in self.heads]
        row=dict(round=rnd,method=self.name,private_seconds=private_s,generation_seconds=generation,
            exchange_seconds=exchange,public_seconds=public,pipeline_seconds=private_s+generation+exchange+public,
            private_loss=float(np.mean(loss)),public_loss=public_loss,
            private_optimizer_steps=sum((len(z)+cfg.private_batch-1)//cfg.private_batch for z in data.private)*cfg.private_epochs,
            public_optimizer_steps=0 if self.name=='Local' else len(self.heads)*cfg.public_epochs*((len(data.edges)+cfg.public_edge_batch-1)//cfg.public_edge_batch),
            private_forward_endpoints=private_points,teacher_forward_endpoints=0 if self.name=='Local' else len(self.heads)*cfg.samples,
            student_forward_endpoints=public_points,head_digest_before_public=pre_public,
            head_digest_after_public=heads_digest(self.heads),traffic=traffic,
            applied_targets_digest=None if record is None else record['applied_targets_digest'])
        return row,snapshots,relations,record

def run(directory,config,*,public_truth=None,probes=True,progress=True,fixture=False):
    config.validate()
    if any(p['num_threads']!=config.threads for p in threadpool_info() if p['user_api']=='blas'):raise ValueError('Unexpected BLAS threads')
    t=perf_counter();data=Prepared(directory,config,allow_test_fixture=fixture);load=perf_counter()-t
    try:
        if public_truth is not None and np.asarray(public_truth).shape!=(config.samples,):raise ValueError('Expected public labels for offline evaluation only')
        truth=None if public_truth is None else hard_relations(np.asarray(public_truth),data.edges)
        methods={name:Branch(name,data,config) for name in NAMES}
        initial={heads_digest(m.heads) for m in methods.values()}
        if len(initial)!=1:raise AssertionError('Initial heads differ')
        records=[];metrics=[];diagnostics=[];target_records=[];probe_s=0.;eval_s=0.
        for rnd in range(1,config.rounds+1):
            checkpoint=(rnd==1 or rnd%config.eval_every==0 or rnd==config.rounds)
            shift=(data.seed+rnd)%4;order=NAMES[shift:]+NAMES[:shift]
            for name in order:
                method=methods[name];row,snapshots,relations,record=method.step(rnd,checkpoint and probes,truth)
                records.append(row)
                if record is not None:target_records.append(record)
                if checkpoint and probes:
                    start=perf_counter();before=heads_digest(method.heads)
                    if relations is None:
                        relations=np.array([hard_relations((z@w.T+b).argmax(axis=1),data.edges) for z,(w,b) in zip(data.public,snapshots)],dtype=np.uint8)
                    diagnostics.extend(probe(data,config,snapshots,relations,rnd,name))
                    if heads_digest(method.heads)!=before:raise AssertionError('Probe changed training heads')
                    probe_s+=perf_counter()-start
            if checkpoint:
                start=perf_counter()
                for name in NAMES:metrics.append(dict(round=rnd,method=name,**evaluate(methods[name].heads,data,config)))
                eval_s+=perf_counter()-start
            if progress and (rnd%10==0 or rnd==config.rounds):print(f'  seed={data.seed} {rnd}/{config.rounds}',flush=True)
        summary={}
        for name,method in methods.items():
            rr=[r for r in records if r['method']==name]
            summary[name]=dict(initialization_seconds=method.initialization_seconds,
                head_pipeline_seconds=method.initialization_seconds+sum(r['pipeline_seconds'] for r in rr),
                **{phase+'_seconds':sum(r[phase+'_seconds'] for r in rr) for phase in ('private','generation','exchange','public')},
                final_head_digest=heads_digest(method.heads),final_metrics=next(q for q in reversed(metrics) if q['method']==name),
                initial_traffic=method.initial_traffic,
                traffic={} if method.protocol is None else method.protocol.traffic.snapshot())
        return dict(seed=data.seed,dataset=data.metadata['dataset'],config=config.json(),
            prepared_directory=str(data.directory.resolve()),initial_head_digest=next(iter(initial)),
            common_preparation_seconds=data.metadata['preparation_wall_seconds_excluding_download'],shared_loading_seconds=load,
            summary=summary,round_records=records,metrics=metrics,diagnostics=diagnostics,target_records=target_records,
            validation=dict(mismatches=0,target_records_checked=len(target_records),
                teacher_relation_entries=len(target_records)*len(config.dimensions)*len(data.edges),
                probe_rows=len(diagnostics),probes_enabled=probes,probe_seconds_excluded=probe_s,evaluation_seconds_excluded=eval_s,
                scope='Exact target construction/replay and read-only probes; this is not a D/E performance benchmark'))
    finally:data.close()
