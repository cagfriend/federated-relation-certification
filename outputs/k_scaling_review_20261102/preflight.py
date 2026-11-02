import json
from dataclasses import replace
from pathlib import Path
from threadpoolctl import threadpool_limits
from experiments.stl10_repeat_confirmation.run import check_environment
from experiments.stl10_transfer.run import digest,check_run
from experiments.stl10_compute.design import plan as old_plan
from experiments.stl10_repeat_confirmation.run import check_anchor_compute
from experiments.k_scaling.design import plan,schedule
from experiments.k_scaling.run import sources
from experiments.k_scaling import data
from experiments.k_scaling.engine import run

ROOT=Path.cwd();OUT=ROOT/'outputs/k_scaling_review_20261102'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
check_environment(read(ROOT/'experiments/stl10_repeat_confirmation/results_full/environment.json'))
original=old_plan('full')[0];anchors=0
for seed in (1001,1002,1003):
 for part in ('iid','dirichlet_0.1'):
  marker=read(ROOT/f'experiments/stl10_transfer/results_full/prepared_{part}_seed_{seed}.json');base=Path(marker['path'])
  if digest(base/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Base metadata changed')
  metadata=read(base/'prepared.json')
  if (metadata['seed'],metadata['partition'])!=(seed,part):raise ValueError('Base identity mismatch')
  r=read(ROOT/f'experiments/stl10_compute/results_full/runs/{part}_{original.case_id}_seed_{seed}_B.json')
  check_run(r,dict(seed=seed,partition=part,method='B',case_id=original.case_id),original,base,False);anchors+=1
  if seed==1002 and part=='iid':reference,selected_base=r,base
spec=plan('full')[0];prefix=replace(spec,config=replace(spec.config,rounds=3))
small=data.prepare(selected_base,prefix,OUT/'preflight_k10')
paths=data.pseudo_paths(small)
if paths!=[selected_base/f'client_{i}_pseudo.npy' for i in range(6)]:raise ValueError('K10 labels not referenced exactly')
with threadpool_limits(limits=1):actual=run(selected_base,prefix,paths,method='B')
expected=dict(reference,round_records=reference['round_records'][:3],metrics=[])
check_anchor_compute(dict(actual,metrics=[]),expected)
if actual['initial_head_digest']!=reference['initial_head_digest'] or actual['graph_sha256']!=reference['graph_sha256']:raise ValueError('Initial state differs')
receipt=dict(result='PASS',old_experiment_sources_unchanged=True,base_markers_verified=6,old_k10_anchors_verified=anchors,
             real_k10_prefix_rounds_exact=3,real_k10_prefix_clients=6,new_kmeans_on_real_data=False,formal_experiment_started=False,
             planned_runs=len(schedule('full')),planned_memory_runs=len(schedule('full',True)),sources=sources())
(OUT/'preflight.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: old frozen sources, six bases and anchors; real K10 three-round six-client prefix exact; no formal experiment started.')
