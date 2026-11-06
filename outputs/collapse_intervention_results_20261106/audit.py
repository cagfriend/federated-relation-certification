import json,csv,tempfile,statistics
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.collapse_intervention.run import read,validate,check_reference,check_environment
from experiments.collapse_intervention.report import reports
from experiments.private_workload.design import spec_from_json
from experiments.stl10_transfer.run import seal,digest
out=Path('experiments/collapse_intervention/results_full');dest=Path('outputs/collapse_intervention_results_20261106')
env=read(out/'environment.json');check_environment(env)
manifest=read(out/'completed.json')
for name,value in manifest['files'].items():assert digest(out/name)==value,name
assert read(out/'finished.json')['completed_manifest_sha256']==digest(out/'completed.json')
anchor=read(out/'historical_public2.json');assert anchor==read(env['anchor_path']);assert seal(dict(anchor))['run_sha256']==anchor['run_sha256']
pre=read(out/'preflight.json');assert seal(dict(pre))['run_sha256']==pre['run_sha256'];check_reference(pre['reference'],anchor)
base=spec_from_json(env['base_spec']);results={};summaries=[];stage_summary=[];trajectories=[]
for arm in ('private_only','public1','public2_half'):
 r=read(out/'runs'/f'{arm}.json');validate(r,base,anchor,expected_arm=arm);results[arm]=r
for arm,r in list(results.items())+[('historical_public2',anchor)]:
 final=r['metrics'][-1];clients=final['clients'];events=[(m['round'],c['client']) for m in r['metrics'] for c in m['clients'] if c['largest_cluster_fraction']>=.99]
 summaries.append(dict(arm=arm,final=final['mean'],mean_largest=statistics.mean(c['largest_cluster_fraction'] for c in clients),worst_largest=max(c['largest_cluster_fraction'] for c in clients),final_single=sum(c['occupied_clusters']==1 for c in clients),final_near=sum(c['largest_cluster_fraction']>=.99 for c in clients),near_events=len(events),near_event_rounds=sorted(set(t[0] for t in events)),min_client_acc=min(c['acc'] for c in clients),occupied_counts=[c['occupied_clusters'] for c in clients],teacher_fraction_final=r['round_records'][-1]['positive_relation_fraction']))
 for rnd in (1,2,5,10,20,40,80,100,140,180,200):
  row=r['round_records'][rnd-1];m=next((m for m in r['metrics'] if m['round']==rnd),None)
  trajectories.append(dict(arm=arm,round=rnd,teacher_positive=row['positive_relation_fraction'],test_mean_largest=None if m is None else statistics.mean(c['largest_cluster_fraction'] for c in m['clients']),test_near=None if m is None else sum(c['largest_cluster_fraction']>=.99 for c in m['clients'])))
 if arm!='historical_public2':
  for stage in r['stages']:
   if stage['round'] in (0,1,2,5,10,20,40,100,200):
    for split in ('private','public'):
     cs=stage['clients'];stage_summary.append(dict(arm=arm,round=stage['round'],phase=stage['phase'],split=split,mean_largest=statistics.mean(c[split]['largest_cluster_fraction'] for c in cs),near=sum(c[split]['largest_cluster_fraction']>=.99 for c in cs),private_fit=statistics.mean(c[split]['pseudo_accuracy'] for c in cs) if split=='private' else None))
with tempfile.TemporaryDirectory(dir=dest) as tmp:
 reports(Path(tmp),results,anchor);generated=[]
 for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
power=[json.loads(line) for p in out.glob('power_*.jsonl') for line in p.read_text(encoding='utf-8').splitlines()];warnings=[x for x in power if x['gap_warning'] or x['ac_line_status']!=1]
for name,rows in [('trajectory.csv',trajectories),('stage_summary.csv',stage_summary)]:
 with (dest/name).open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
a=dict(status='PASS',manifest_files=len(manifest['files']),frozen_sources=len(env['sources']),runs=3,rounds_per_run=200,preflight_rounds=len(pre['reference']['round_records']),report_replay=generated,summary=summaries,power_samples=len(power),power_warnings=warnings,excluded_runs=0,excluded_rounds=0)
(dest/'audit.json').write_text(json.dumps(a,indent=2),encoding='utf-8');print(json.dumps(a));print('FINAL PRIVATE FIT/PROBES',json.dumps([s for s in stage_summary if s['round']==200]))
