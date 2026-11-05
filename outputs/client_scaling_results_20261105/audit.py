import csv,json,sys,tempfile,statistics
from pathlib import Path
R=Path.cwd();sys.path.insert(0,str(R))
from experiments.client_scaling.run import *
from experiments.client_scaling.report import reports
out=R/'experiments/client_scaling/results_full_fixed_total';dest=R/'outputs/client_scaling_results_20261105'
verify_completed(out);env=json.loads((out/'environment.json').read_text(encoding='utf-8'));check_environment(env)
assert digest(out/'completed.json')==json.loads((out/'finished.json').read_text(encoding='utf-8'))['completed_manifest_sha256']
records=[];memory=[];inputs={}
for mem in (False,True):
 for m in schedule('full','fixed_total',memory=mem):
  r=json.loads((out/('memory' if mem else 'runs')/filename(m)).read_text(encoding='utf-8'));s=spec_from_json(env['plan'][spec_key(m)])
  info=json.loads((out/'inputs'/(input_key(m).replace('|','_')+'.json')).read_text(encoding='utf-8'));p=Path(info['path'])
  assert digest(p/'prepared.json')==info['metadata_sha256'];inputs[input_key(m)]=info
  verify_record(r,m,s,p,mem,False)
  if mem:
   base=next(z for x,z in records if all(x[k]==m[k] for k in IDENTITY));assert non_time_rows(r)==non_time_rows(base)
   memory.append((m,r))
  else: records.append((m,r))
groups=verify_groups(records);anchors=0
for m,r in records:
 if m['clients']==6 and m['method']=='B':
  a=json.loads((R/'experiments/stl10_compute/results_full/runs'/f"{m['partition']}_{r['case_id']}_seed_{m['seed']}_B.json").read_text(encoding='utf-8'));check_anchor_compute(r,a);assert r['initial_head_digest']==a['initial_head_digest'];anchors+=1
with tempfile.TemporaryDirectory(dir=dest) as temp:
 reports(Path(temp),records,memory,fixture=False);reports_checked=[]
 for p in Path(temp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes();reports_checked.append(p.name)
quality=[];spikes=[]
for m,r in records:
 if m['method']=='B':
  q=r['metrics'][-1];quality.append(dict(seed=m['seed'],partition=m['partition'],N=m['clients'],mean=q['mean'],single=[c['client'] for c in q['clients'] if c['occupied_clusters']==1],near=[c['client'] for c in q['clients'] if c['largest_cluster_fraction']>=.99]))
 for phase in ('generation','private','public','exchange','pipeline'):
  rows=r['round_records'][1:] if phase in ('generation','pipeline') else r['round_records'];med=statistics.median(x[phase+'_seconds'] for x in rows)
  for row in rows:
   if row[phase+'_seconds']>max(2,10*med):spikes.append(dict(**m,round=row['round'],phase=phase,seconds=row[phase+'_seconds'],median=med))
power=[json.loads(s) for p in out.glob('power_*.jsonl') for s in p.read_text(encoding='utf-8').splitlines()];warnings=[x for x in power if x['gap_warning'] or x['ac_line_status']!=1]
result=dict(status='PASS',runs=len(records),memory=len(memory),triples=len(groups),anchors=anchors,manifest_files=len(json.loads((out/'completed.json').read_text(encoding='utf-8'))['files']),sources=len(env['sources']),reports_checked=reports_checked,relations=sum(r['validation']['relation_comparisons'] for _,r in records),candidates=sum(r['validation']['candidate_membership_comparisons'] for _,r in records),mismatches=0,quality=quality,timing_flags=spikes,power_samples=len(power),power_warnings=warnings,excluded_runs=0,excluded_rounds=0)
(dest/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

