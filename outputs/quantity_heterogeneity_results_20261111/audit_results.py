from pathlib import Path
import sys,json,tempfile,csv,statistics
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R))
from experiments.quantity_heterogeneity.run import check_environment,verify_record,verify_groups,non_time_rows,_validate_equal_anchors,_compare_equal_anchor
from experiments.quantity_heterogeneity.design import schedule,filename,input_key,plan
from experiments.quantity_heterogeneity.report import reports
from experiments.quantity_heterogeneity import data
from experiments.stl10_transfer.run import digest
H=Path(__file__).parent;out=R/'experiments/quantity_heterogeneity/results_full'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
env=read(out/'environment.json');check_environment(env);check_environment(read(out/'environment_final.json'))
manifest=read(out/'completed.json')
for name,h in manifest['files'].items():assert digest(out/name)==h,name
assert read(out/'finished.json')['completed_manifest_sha256']==digest(out/'completed.json')
anchors,anchor_sources=_validate_equal_anchors(R/'experiments/lr_client_scaling/results_full_fixed_per_client','full',False)
assert env['equal_anchor_sources']==anchor_sources
for key,e in env['inputs'].items():
 seed,part,profile=key.split('|');assert digest(Path(e['path'])/'prepared.json')==e['metadata_sha256']
 data.verify(e['path'],plan('full')[profile],int(seed),part,profile=profile,fixture=False)
 print('Validated input '+key,flush=True)
normal=[];memory=[];flags=[]
for mem,target in ((False,normal),(True,memory)):
 jobs=schedule('full',memory=mem)
 assert {p.name for p in (out/('memory' if mem else 'runs')).glob('*.json')}=={filename(m) for m in jobs}
 for meta in jobs:
  r=read(out/('memory' if mem else 'runs')/filename(meta));spec=plan('full')[meta['profile']]
  entry=env['inputs'][input_key(meta)]
  verify_record(r,meta,spec,entry['path'],mem,False);target.append((meta,r))
  assert r['worker_ended_utc']>=r['worker_started_utc'] and r['engine_wall_seconds']>0
  assert r['worker_started_power']['ac_line_status']==r['worker_ended_power']['ac_line_status']==1
  if mem:
   ref=next(v for m,v in normal if all(meta[k]==m[k] for k in ('seed','partition','profile','method')))
   assert non_time_rows(r)==non_time_rows(ref)
   for f in ('persistent_method_array_bytes','initial_traffic','traffic'):assert r['summary'][meta['method']][f]==ref['summary'][meta['method']][f]
  else:
   if meta['profile']=='equal':_compare_equal_anchor(r,meta,anchors)
   for phase in ('private','generation','exchange','public','pipeline'):
    rows=r['round_records'][1:] if phase in ('generation','pipeline') else r['round_records']
    med=statistics.median(x[phase+'_seconds'] for x in rows)
    for row in rows:
     if row[phase+'_seconds']>max(2,10*med):flags.append(dict(profile=meta['profile'],partition=meta['partition'],seed=meta['seed'],method=meta['method'],round=row['round'],phase=phase,seconds=row[phase+'_seconds'],median=med))
groups=verify_groups(normal)
with tempfile.TemporaryDirectory(dir=H) as tmp:
 reports(Path(tmp),normal,memory,fixture=False);generated=[]
 for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
def csvread(name):
 with (out/name).open(encoding='utf-8') as f:return list(csv.DictReader(f))
pairs=csvread('paired_cost.csv');quality=csvread('quality_guardrails.csv');clients=csvread('private_capacities.csv')
for p in pairs:
 profile=p['regime'].replace('quantity_','');g=groups[(profile,p['partition'],int(p['seed']))];ref=p['comparison'][-1]
 assert float(p['head_ratio'])==g['D']['summary']['D']['head_pipeline_seconds']/g[ref]['summary'][ref]['head_pipeline_seconds']
power=[json.loads(l) for p in out.glob('power_*.jsonl') for l in p.read_text(encoding='utf-8').splitlines()]
bad=[p for p in pairs if float(p['head_ratio'])>=1]
severe=[c for c in clients if int(c['final_occupied_clusters'])==1 or float(c['final_largest_cluster_fraction'])>=.99]
memory_pairs=[]
for meta,r in memory:
 if meta['method']!='D':continue
 for ref in ('B','E'):
  b=next(v for m,v in memory if m['method']==ref and m['partition']==meta['partition'])
  memory_pairs.append(dict(partition=meta['partition'],comparison='D/'+ref,peak_ratio=r['process_peak_bytes']/b['process_peak_bytes']))
res=dict(status='PASS',runs=len(normal),memory_runs=len(memory),groups=len(groups),inputs=len(env['inputs']),manifest_files=len(manifest['files']),frozen_sources=len(env['sources']),reports_reproduced=sorted(generated),relations=sum(r['validation']['relation_comparisons'] for m,r in normal),candidates=sum(r['validation']['candidate_membership_comparisons'] for m,r in normal),mismatches=0,equal_P3_method_anchors_matched=18,negative_head_pairs=bad,severe_final_clients=severe,severe_cases={p:sum(q['profile']==p and q['severe_final_collapse']=='True' for q in quality) for p in ('equal','moderate','strong')},power_samples=len(power),power_warnings=[r for r in power if r['gap_warning'] or r['ac_line_status']!=1],timing_flags=flags,excluded_runs=0,excluded_rounds=0,memory_pairs=memory_pairs)
(H/'audit.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res))
