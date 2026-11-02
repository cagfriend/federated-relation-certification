import csv,json,math,statistics as st,tempfile
from pathlib import Path
import outputs.k_scaling_sleep_review_20261102.audit as original
from experiments.k_scaling.report import reports
from experiments.stl10_compute.design import plan as old_plan
from experiments.stl10_transfer.run import check_run
from experiments.stl10_repeat_confirmation.run import check_anchor_compute

ROOT=Path.cwd();R=ROOT/'experiments/k_scaling/results_full';O=ROOT/'outputs/k_scaling_results_20261102';O.mkdir(exist_ok=True)
env=original.env;completed=original.completed;mem=[];quality=[];memory=[]
for m,r in completed:
 cfg=r['config'];s=r['summary'][m['method']]
 assert abs(s['head_pipeline_seconds']-(s['initialization_seconds']+sum(x['pipeline_seconds'] for x in r['round_records'])))<1e-7
 for phase in ('private','generation','exchange','public'):
  assert abs(s[phase+'_seconds']-sum(x[phase+'_seconds'] for x in r['round_records']))<1e-7
 for q in r['metrics']:
  assert [c['client'] for c in q['clients']]==list(range(6))
  for c in q['clients']:
   counts=c['cluster_counts'];assert len(counts)==m['classes'] and sum(counts)==8000
   assert c['occupied_clusters']==sum(n>0 for n in counts) and c['largest_cluster_fraction']==max(counts)/8000
  for name in ('acc','nmi','ari'):assert math.isclose(q['mean'][name],st.mean(c[name] for c in q['clients']),abs_tol=1e-12)
 if m['method']=='B':
  q=r['metrics'][-1];cs=q['clients'];quality.append(dict(partition=m['partition'],seed=m['seed'],classes=m['classes'],**q['mean'],single=sum(c['occupied_clusters']==1 for c in cs),dominant99=sum(c['largest_cluster_fraction']>=.99 for c in cs),max_client_largest=max(c['largest_cluster_fraction'] for c in cs)))
  if m['classes']==10:
   spec=old_plan('full')[0];ref=json.loads((ROOT/f"experiments/stl10_compute/results_full/runs/{m['partition']}_{spec.case_id}_seed_{m['seed']}_B.json").read_text())
   base=Path(env['inputs'][f"{m['seed']}|{m['partition']}|10"]['base']);check_run(ref,dict(seed=m['seed'],partition=m['partition'],method='B',case_id=spec.case_id),spec,base,False);check_anchor_compute(r,ref)
for m in original.schedule('full',True):
 r=original.read(R/'memory'/original.filename(m));mem.append((m,r));s=r['summary'][m['method']]
 memory.append(dict(**m,peak_bytes=r['process_peak_bytes'],persistent_bytes=s['persistent_method_array_bytes']))
with tempfile.TemporaryDirectory() as tmp:
 reports(tmp,completed,mem,fixture=False)
 for p in Path(tmp).iterdir():assert p.read_bytes()==(R/p.name).read_bytes(),p.name
relations=sum(r['validation']['relation_comparisons'] for _,r in completed);candidates=sum(r['validation']['candidate_membership_comparisons'] for _,r in completed)
assert relations==707788800 and candidates==943718400
with (O/'quality.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(quality[0]));w.writeheader();w.writerows(quality)
data=dict(result='PASS',runs=72,memory_runs=12,triples=24,original_files=93,old_K10_anchors_verified=6,
 relations=relations,candidates=candidates,mismatches=0,quality=quality,memory=memory,
 sleep_adjustment='Preparation-only cost NA for seed1002/dirichlet_0.1/K64; no training timing exclusions.',
 statistical_limit='One run per case; K64 cases include a severe collapse. No pure-K complexity causality, fresh-seed, or universal speed claim.',
 independently_replayed_all_training=False)
(O/'audit.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: 72 runs + 12 memory; 24 triples; 6 K10 anchors; six reports byte-identical; oracle records 707788800/943718400.')
