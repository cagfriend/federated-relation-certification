import json,statistics as st
from pathlib import Path
from experiments.stl10_transfer.run import digest,seal,check_environment
from experiments.stl10_public_steps.run import sources,validate
from experiments.private_workload.design import spec_from_json
from experiments.stl10_diagnostics.run import compare_anchor
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments/stl10_public_steps/results_full'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
m=read(OUT/'completed.json');env=read(OUT/'environment.json')
assert m['public_budgets']==[1,2,4,8] and m['rounds']==40 and m['runs']==4
assert all(digest(OUT/p)==h for p,h in m['files'].items())
assert env['source_hashes']==sources()
source=Path(env['source_results']);check_environment(read(source/'environment.json'))
results={}
for s in env['specs']:
 spec=spec_from_json(s);r=read(OUT/f'public_steps_{spec.steps}.json');validate(r,spec,40)
 assert r['spec']==s and r['public_steps']==spec.steps
 assert seal(dict(r))['run_sha256']==r['run_sha256']
 assert len(r['metrics'])==7 and len(r['stages'])==40 and len(r['gradients'])==36
 results[spec.steps]=r
assert len({r['initial_head_digest'] for r in results.values()})==1
for r in results.values():
 for a,b in zip(r['round_records'],results[8]['round_records']):
  for k in ('private_subset_digest','private_samples_per_client','private_subset_pseudo_histograms','private_optimizer_steps','private_forward_endpoints'):assert a[k]==b[k]
anchor=source/'runs'/'iid_m16384_fixed8_privfull_seed_1001_B.json'
assert digest(anchor)==env['anchor_sha256'];compare_anchor(results[8],read(anchor))
summary=[]
for steps,r in results.items():
 q=r['metrics'][-1];after=r['stages'][-1]['after_public']
 summary.append(dict(public_steps=steps,final_acc=q['mean']['acc'],final_nmi=q['mean']['nmi'],final_ari=q['mean']['ari'],final_test_single_cluster_clients=sum(c['occupied_clusters']==1 for c in q['clients']),max_single_cluster_clients_at_recorded_test_checkpoints=max(sum(c['occupied_clusters']==1 for c in q['clients']) for q in r['metrics']),final_public_probe_max_fraction_mean=st.mean(c['public']['largest_cluster_fraction'] for c in after),final_private_pseudo_accuracy_mean=st.mean(c['private']['pseudo_accuracy'] for c in after),teacher_positive_fraction_final=r['round_records'][-1]['positive_relation_fraction']))
receipt=dict(status='passed',manifest_files_verified=len(m['files']),sealed_runs=4,rounds_each=40,eight_step_anchor_rounds=40,private_workload_identical=True,old_sources_unchanged=True,summary=summary)
(Path(__file__).parent/'AUDIT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt,indent=2))
