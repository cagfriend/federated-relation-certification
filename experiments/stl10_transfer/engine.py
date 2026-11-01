"""Reuse original training steps; adapt only dataset loading and orchestration."""
import hashlib,os
from time import perf_counter
import numpy as np
from threadpoolctl import threadpool_info
from experiments.public_scaling.data import Prepared as CorePrepared
from experiments.public_scaling.engine import audit,evaluate,heads_digest
from experiments.private_workload.engine import WorkloadMethod
from experiments.private_workload.student import Coverage
from .data import verify

def run(directory,spec,method,*,fixture=False):
 spec.validate();cfg=spec.config
 if method not in ('B','E','D'):raise ValueError('Unknown method')
 if any(x['num_threads']!=cfg.threads for x in threadpool_info() if x['user_api']=='blas'):raise ValueError('Unexpected BLAS threads')
 import json
 from pathlib import Path
 meta=json.loads((Path(directory)/'prepared.json').read_text(encoding='utf-8'))
 verify(directory,cfg,meta['seed'],meta['partition'],fixture=fixture)
 expected='STL-10 fixture' if fixture else 'STL-10'
 if meta['dataset']!=expected:raise ValueError('Dataset identity mismatch')
 # Core reader checks shapes and config. Its dataset allow flag is enabled only
 # after the dedicated STL verifier has checked source assets and real/fixture identity.
 t=perf_counter();data=CorePrepared(directory,cfg,allow_test_fixture=True);loading=perf_counter()-t
 try:
  m=WorkloadMethod(method,data,spec);initial=heads_digest(m.heads);observer=Coverage(len(cfg.dimensions),data.edges,cfg.samples)
  rr=[];metrics=[];coverage=[];checks=members=0;audits=evals=0.
  for rnd in range(1,cfg.rounds+1):
   row,relations,snapshots,orders=m.step(rnd);rr.append(row)
   if any(h!=row['committed_counts_digest'] for h in row['received_counts_digests']):raise AssertionError('Received target mismatch')
   t=perf_counter();a,b=audit(m,relations,snapshots,data);checks+=a;members+=b
   coverage.append(dict(round=rnd,**observer.observe(orders)));audits+=perf_counter()-t
   if rnd%cfg.eval_every==0 or rnd==cfg.rounds:
    t=perf_counter();metrics.append(dict(round=rnd,method=method,**evaluate(m.heads,data,cfg)));evals+=perf_counter()-t
  pipeline=m.initialization_seconds+sum(r['pipeline_seconds'] for r in rr);gen=sum(r['generation_seconds'] for r in rr)
  summary=dict(initialization_seconds=m.initialization_seconds,head_pipeline_seconds=pipeline,
   with_shared_preparation_seconds=meta['preparation_wall_seconds_excluding_download']+loading+pipeline,
   **{p+'_seconds':sum(r[p+'_seconds'] for r in rr) for p in ('private','generation','exchange','public')},
   generation_fraction=gen/pipeline,teacher_recompute_fraction=None if cfg.rounds==1 else sum(r['teacher_forward_endpoints'] for r in rr[1:])/(cfg.samples*len(cfg.dimensions)*(cfg.rounds-1)),
   persistent_method_array_bytes=m.persistent_bytes(),initial_traffic=m.initial_traffic,traffic=m.protocol.traffic.snapshot(),
   public_optimizer_steps=sum(r['public_optimizer_steps'] for r in rr),student_forward_endpoints=sum(r['student_forward_endpoints'] for r in rr),
   private_optimizer_steps=sum(r['private_optimizer_steps'] for r in rr),private_forward_endpoints=sum(r['private_forward_endpoints'] for r in rr),
   private_samples_per_client=rr[0]['private_samples_per_client'],final_head_digest=heads_digest(m.heads),final_metrics=metrics[-1])
  return dict(seed=data.seed,dataset=meta['dataset'],config=cfg.json(),spec=spec.json(),case_id=spec.case_id,
   initial_head_digest=initial,graph_sha256=hashlib.sha256(data.edges.astype('<u4').tobytes()).hexdigest(),prepared_directory=str(data.directory.resolve()),
   common_preparation_seconds=meta['preparation_wall_seconds_excluding_download'],shared_loading_seconds=loading,summary={method:summary},
   round_records=rr,metrics=metrics,coverage=observer.snapshot(),coverage_records=coverage,
   validation=dict(enabled=True,mismatches=0,relation_comparisons=checks,candidate_membership_comparisons=members,audit_and_coverage_seconds_excluded=audits,evaluation_seconds_excluded=evals),process=dict(pid=os.getpid()))
 finally:data.close()
