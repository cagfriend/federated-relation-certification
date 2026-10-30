"""Reuse accepted B/E/D steps; Local performs private SGD only."""
from time import perf_counter
import numpy as np
from threadpoolctl import threadpool_info

from experiments.public_scaling.engine import Method,audit,evaluate,heads_digest
from experiments.public_scaling.head import private_epoch
from experiments.public_scaling.data import Prepared

NAMES=('Local','B','E','D')


class LocalMethod(Method):
    def __init__(self,data,config):super().__init__('Local',data,config)

    def step(self,rnd):
        start=perf_counter();losses=[];points=0
        for client,head in enumerate(self.heads):
            loss,count=private_epoch(head,self.data.private[client],self.data.pseudo[client],
                self.config,self.data.seed,client,rnd)
            losses.append(loss);points+=count
        private=perf_counter()-start
        return dict(method='Local',round=rnd,private_seconds=private,generation_seconds=0.,
            exchange_seconds=0.,public_seconds=0.,pipeline_seconds=private,
            private_loss=float(np.mean(losses)),public_loss=None,
            private_forward_endpoints=points,student_forward_endpoints=0,
            private_optimizer_steps=sum((len(z)+self.config.private_batch-1)//self.config.private_batch
                for z in self.data.private)*self.config.private_epochs,
            public_optimizer_steps=0,positive_relation_fraction=None,teacher_forward_endpoints=0,
            certified_edges_before_refresh=0,client_statistics=[],traffic={},
            head_digest_after_public=heads_digest(self.heads),persistent_method_array_bytes=self.persistent_bytes()),[],[]


def run(directory,config,*,names=NAMES,validate=True,metrics=True,progress=True,fixture=False):
    config.validate()
    if not names or len(set(names))!=len(names) or any(n not in NAMES for n in names):raise ValueError('Invalid methods')
    if any(p['num_threads']!=config.threads for p in threadpool_info() if p['user_api']=='blas'):
        raise ValueError('Unexpected BLAS thread count')
    t=perf_counter();data=Prepared(directory,config,allow_test_fixture=fixture);load=perf_counter()-t
    try:
        shift=data.seed%len(names);methods={}
        for name in names[shift:]+names[:shift]:
            methods[name]=LocalMethod(data,config) if name=='Local' else Method(name,data,config)
        initial={heads_digest(m.heads) for m in methods.values()}
        if len(initial)!=1:raise AssertionError('Different initial heads')
        rows=[];quality=[];checks=0;members=0;audit_s=0.;eval_s=0.
        for rnd in range(1,config.rounds+1):
            outputs={};rr={};shift=(data.seed+rnd)%len(names)
            for name in names[shift:]+names[:shift]:
                row,relations,snapshots=methods[name].step(rnd)
                rows.append(row);rr[name]=row;outputs[name]=(relations,snapshots)
            collaborators=[n for n in names if n!='Local']
            if validate:
                t=perf_counter()
                if len({rr[n]['head_digest_after_public'] for n in collaborators})>1:
                    raise AssertionError('B/E/D training diverged')
                if collaborators and any(rr[n]['traffic']!=rr[collaborators[0]]['traffic'] for n in collaborators):
                    raise AssertionError('B/E/D traffic differs')
                for name in collaborators:
                    count,membership=audit(methods[name],*outputs[name],data)
                    checks+=count;members+=membership
                audit_s+=perf_counter()-t
            if metrics and (rnd%config.eval_every==0 or rnd==config.rounds):
                t=perf_counter()
                for name in names:quality.append(dict(method=name,round=rnd,**evaluate(methods[name].heads,data,config)))
                same=[q for q in quality if q['round']==rnd and q['method'] in collaborators]
                if validate and same and any(q['clients']!=same[0]['clients'] for q in same):
                    raise AssertionError('B/E/D evaluation differs')
                eval_s+=perf_counter()-t
            if progress and (rnd%10==0 or rnd==config.rounds):
                print(f'  seed={data.seed}: {rnd}/{config.rounds}',flush=True)
        summary={}
        for name in names:
            method=methods[name];rr=[r for r in rows if r['method']==name]
            training=method.initialization_seconds+sum(r['pipeline_seconds'] for r in rr)
            summary[name]=dict(initialization_seconds=method.initialization_seconds,
                head_pipeline_seconds=training,
                shared_preparation_plus_head_seconds=data.metadata['preparation_wall_seconds_excluding_download']+load+training,
                **{phase+'_seconds':sum(r[phase+'_seconds'] for r in rr) for phase in ('private','generation','exchange','public')},
                refresh_fraction=None if name=='Local' or config.rounds==1 else
                    sum(r['teacher_forward_endpoints'] for r in rr[1:])/(config.samples*len(config.dimensions)*(config.rounds-1)),
                persistent_method_array_bytes=method.persistent_bytes(),
                traffic={} if method.protocol is None else method.protocol.traffic.snapshot(),
                final_head_digest=heads_digest(method.heads),
                final_metrics=next((q for q in reversed(quality) if q['method']==name),None))
        return dict(seed=data.seed,config=config.json(),initial_head_digest=next(iter(initial)),
            prepared_directory=str(data.directory.resolve()),dataset=data.metadata['dataset'],
            common_preparation_seconds=data.metadata['preparation_wall_seconds_excluding_download'],
            shared_loading_seconds=load,
            preparation_public_feature_stage_seconds=sum(c['public_feature_seconds'] for c in data.metadata.get('clients',[])),
            round_records=rows,metrics=quality,summary=summary,
            validation=dict(enabled=validate,mismatches=0 if validate else None,
                relation_comparisons=checks,candidate_membership_comparisons=members,
                audit_seconds_excluded=audit_s,evaluation_seconds_excluded=eval_s))
    finally:data.close()
