import json,statistics as st
from pathlib import Path
import numpy as np
from experiments.stl10_transfer.run import digest,seal,check_environment
from experiments.stl10_diagnostics.run import compare_anchor,target_digest
from experiments.private_workload.design import spec_from_json
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments/stl10_diagnostics/results_full'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
m=read(OUT/'completed.json');env=read(OUT/'environment.json')
assert m['rounds']==40 and m['runs']==3 and m['j_anchor_rounds_matched']==40 and m['j_f_round1_matched']
assert all(digest(OUT/p)==h for p,h in m['files'].items())
assert all(digest(ROOT/p)==h for p,h in env['diagnostic_sources'].items())
source=Path(env['source_results']);check_environment(read(source/'environment.json'))
arms={a:read(OUT/f'{a}.json') for a in ('P','J','F')}
assert len({r['initial_head_digest'] for r in arms.values()})==1
for a,r in arms.items():
 assert seal(dict(r))['run_sha256']==r['run_sha256']
 assert [v['round'] for v in r['round_records']]==list(range(1,41))
 assert len(r['stages'])==40 and len(r['gradients'])==36
 assert r['final_head_digest']==r['round_records'][-1]['head_digest_after_public']
anchor=source/'runs'/f"iid_{spec_from_json(env['spec']).case_id}_seed_1001_B.json"
assert digest(anchor)==env['anchor_sha256'];compare_anchor(arms['J'],read(anchor))
assert arms['J']['round_records'][0]['head_digest_after_public']==arms['F']['round_records'][0]['head_digest_after_public']
fixed=np.load(OUT/'fixed_round1_targets.npy',allow_pickle=False)
for row in arms['F']['round_records']:
 for c,t in enumerate(row['student_targets']):assert t['digest']==target_digest(fixed[c])
assert all(v['public_optimizer_steps']==v['student_forward_endpoints']==0 for v in arms['P']['round_records'])
inspection=read(OUT/'initial_inspection.json')['clients']
init=[]
for c in inspection:
 hist=c['private_pseudo_histogram']
 init.append(dict(client=c['client'],pseudo_occupied=sum(n>0 for n in hist),pseudo_max=max(hist)/sum(hist),center_mismatches=c['private_pseudo_nearest_center_mismatches'],center_test_acc=c['test_center_metrics']['acc'],center_test_max=c['test_center_probe']['largest_cluster_fraction'],private_feature_spread=c['private_features']['spread_to_mean_scale'],public_feature_spread=c['public_features']['spread_to_mean_scale'],test_feature_spread=c['test_features']['spread_to_mean_scale']))
summaries={}
for a,r in arms.items():
 stage=[]
 for rnd in (1,2,5,10,20,40):
  item=r['stages'][rnd-1];d=dict(round=rnd)
  for phase in ('before_private','after_private','after_public'):
   cs=item[phase]
   if cs:
    d[phase]=dict(public_mean_max=st.mean(c['public']['largest_cluster_fraction'] for c in cs),private_mean_max=st.mean(c['private']['largest_cluster_fraction'] for c in cs),private_pseudo_accuracy=st.mean(c['private']['pseudo_accuracy'] for c in cs))
  gr=[x for x in r['gradients'] if x['round']==rnd]
  d['gradient_cosine_mean']=st.mean(x['gradient_cosine'] for x in gr if x['gradient_cosine'] is not None)
  d['public_private_update_ratio_median']=st.median(x['public_weighted_update_norm']/x['private_update_norm'] for x in gr if x['private_update_norm']>0)
  stage.append(d)
 summaries[a]=dict(final_test=r['metrics'][-1],stage_checkpoints=stage,teacher_positive_first=r['round_records'][0]['positive_relation_fraction'],teacher_positive_last=r['round_records'][-1]['positive_relation_fraction'])
receipt=dict(status='passed',manifest_files=len(m['files']),j_anchor_rounds=40,fixed_targets_all_rounds_verified=True,initial_inspection=init,arms=summaries)
(Path(__file__).parent/'AUDIT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(dict(status='passed',initial=init,arms={a:{'final_acc':r['final_test']['mean']['acc'],'first':r['stage_checkpoints'][0],'last':r['stage_checkpoints'][-1],'teacher_positive_first':r['teacher_positive_first'],'teacher_positive_last':r['teacher_positive_last']} for a,r in summaries.items()}),indent=2))
