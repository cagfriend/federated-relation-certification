from pathlib import Path
import sys,json,csv,tempfile,statistics
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.lr_client_scaling.run import check_environment,verify_record,verify_groups,non_time_rows,input_key,spec_key
from experiments.lr_client_scaling.design import schedule,filename
from experiments.lr_client_scaling.report import reports
from experiments.private_workload.design import spec_from_json
from experiments.client_scaling import data
from experiments.stl10_transfer.run import digest

out=ROOT/'experiments/lr_client_scaling/results_full_fixed_per_client';dest=Path(__file__).parent
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
env=read(out/'environment.json');check_environment(env)
check_environment(read(out/'environment_final.json'))
manifest=read(out/'completed.json')
for p,h in manifest['files'].items():assert digest(out/p)==h,p
assert read(out/'finished.json')['completed_manifest_sha256']==digest(out/'completed.json')
prepared={};public_ids={}
import numpy as np
for m in schedule('full'):
 key=input_key(m)
 if key in prepared:continue
 marker=read(out/'inputs'/(key.replace('|','_')+'.json'));directory=Path(marker['path'])
 assert digest(directory/'prepared.json')==marker['metadata_sha256']
 s=spec_from_json(env['plan'][spec_key(m)])
 data.verify(directory,s,m['seed'],m['partition'],fixture=False)
 ids=np.load(directory/'public_ids.npy',allow_pickle=False);pk=m['seed'],m['partition']
 if pk in public_ids:assert np.array_equal(ids,public_ids[pk])
 public_ids[pk]=ids;prepared[key]=directory
 print('Validated input '+key,flush=True)
normal=[];memory=[];flags=[]
for mem,target in ((False,normal),(True,memory)):
 jobs=schedule('full',memory=mem)
 assert {p.name for p in (out/('memory' if mem else 'runs')).glob('*.json')}=={filename(m) for m in jobs}
 for meta in jobs:
  r=read(out/('memory' if mem else 'runs')/filename(meta));spec=spec_from_json(env['plan'][spec_key(meta)])
  verify_record(r,meta,spec,prepared[input_key(meta)],mem,False);target.append((meta,r))
  assert r['worker_started_power']['ac_line_status']==r['worker_ended_power']['ac_line_status']==1
  if mem:
   ref=next(r for m,r in normal if all(meta[k]==m[k] for k in ('seed','partition','clients','method','regime')))
   assert non_time_rows(r)==non_time_rows(ref)
   assert r['initial_head_digest']==ref['initial_head_digest']
   assert r['summary'][meta['method']]['persistent_method_array_bytes']==ref['summary'][meta['method']]['persistent_method_array_bytes']
  else:
   for phase in ('private','generation','exchange','public','pipeline'):
    rows=r['round_records'][1:] if phase in ('generation','pipeline') else r['round_records']
    med=statistics.median(x[phase+'_seconds'] for x in rows)
    for row in rows:
     if row[phase+'_seconds']>max(2,10*med):flags.append(dict(clients=meta['clients'],partition=meta['partition'],seed=meta['seed'],method=meta['method'],round=row['round'],phase=phase,seconds=row[phase+'_seconds'],median=med))
groups=verify_groups(normal)
with tempfile.TemporaryDirectory(dir=dest) as tmp:
 reports(Path(tmp),normal,memory,fixture=False);generated=[]
 for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
pairs=list(csv.DictReader((out/'paired_cost.csv').open(encoding='utf-8')))
for row in pairs:
 g=groups[(row['regime'],int(row['clients']),int(row['seed']),row['partition'])];ref=row['comparison'][-1]
 assert float(row['head_ratio'])==g['D']['summary']['D']['head_pipeline_seconds']/g[ref]['summary'][ref]['head_pipeline_seconds']
quality=list(csv.DictReader((out/'quality_guardrails.csv').open(encoding='utf-8')))
events=list(csv.DictReader((out/'collapse_events.csv').open(encoding='utf-8')))
power=[];pwr_summary=[]
for p in out.glob('power_*.jsonl'):
 rows=[json.loads(l) for l in p.read_text(encoding='utf-8').splitlines()];power+=rows
 pwr_summary.append(dict(file=p.name,samples=len(rows),first_utc=rows[0]['utc'],last_utc=rows[-1]['utc']))
memory_pairs=[]
for m,r in memory:
 if m['method']!='D':continue
 for ref in ('B','E'):
  b=next(x for mm,x in memory if mm['clients']==m['clients'] and mm['partition']==m['partition'] and mm['seed']==m['seed'] and mm['method']==ref)
  memory_pairs.append(dict(clients=m['clients'],partition=m['partition'],comparison='D/'+ref,peak_ratio=r['process_peak_bytes']/b['process_peak_bytes'],D_persistent=r['summary']['D']['persistent_method_array_bytes'],ref_persistent=b['summary'][ref]['persistent_method_array_bytes']))
stats=[]
for n in (2,6,12):
 for part in ('iid','dirichlet_0.1'):
  v={c:[float(p['head_ratio']) for p in pairs if int(p['clients'])==n and p['partition']==part and p['comparison']==c] for c in ('D/B','D/E')}
  stats.append(dict(clients=n,partition=part,**{c:dict(median_saving_pct=100*(1-statistics.median(v[c])),wins=sum(x<1 for x in v[c]),range=v[c]) for c in v}))
res=dict(status='PASS',runs=len(normal),memory_runs=len(memory),triples=len(groups),validated_inputs=len(prepared),manifest_files=len(manifest['files']),frozen_sources=len(env['sources']),relations=sum(r['validation']['relation_comparisons'] for m,r in normal),candidates=sum(r['validation']['candidate_membership_comparisons'] for m,r in normal),mismatches=0,reports_reproduced=sorted(generated),quality_trajectories=len(quality),final_severe_cases=sum(x['severe_final_collapse']=='True' for x in quality),intermediate_single_cases=sum(int(x['any_checkpoint_single_clients'])>0 for x in quality),unique_B_collapse_events=[e for e in events if e['method']=='B'],power_invocations=pwr_summary,power_warnings=[r for r in power if r['gap_warning'] or r['ac_line_status']!=1],timing_flags=flags,excluded_runs=0,excluded_rounds=0,case_statistics=stats,memory_pairs=memory_pairs)
(dest/'audit.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res))
