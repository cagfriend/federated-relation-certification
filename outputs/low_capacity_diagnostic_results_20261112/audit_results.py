from pathlib import Path
import sys,json,tempfile,hashlib,statistics
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R))
from experiments.low_capacity_diagnostic.run import check_environment,verify_record,baseline_compare,read,source_snapshot
from experiments.low_capacity_diagnostic.design import plan,schedule,filename
from experiments.low_capacity_diagnostic.report import reports,recovery
from experiments.quantity_heterogeneity import data
H=Path(__file__).parent;out=R/'experiments/low_capacity_diagnostic/results_full';env=read(out/'environment.json');check_environment(env);check_environment(read(out/'environment_final.json'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(out/'completed.json')
for name,h in manifest['files'].items():assert sha(out/name)==h,name
assert read(out/'finished.json')['completed_manifest_sha256']==sha(out/'completed.json')
assert env['source_snapshot']==source_snapshot(Path(env['source_results']))
for cid,e in env['inputs'].items():
 assert sha(Path(e['path'])/'prepared.json')==e['metadata_sha256'] and sha(Path(e['reference_path']))==e['reference_sha256']
 ref=read(e['reference_path']);data.verify(e['path'],plan('full')['baseline'],ref['seed'],ref['partition'],profile='strong',fixture=False)
 print('Verified original input '+cid,flush=True)
references={};completed=[];late=[];verdict={};warnings=[]
jobs=schedule('full');assert {p.name for p in (out/'runs').glob('*.json')}=={filename(m) for m in jobs}
for meta in jobs:
 e=env['inputs'][meta['case_id']];ref=read(e['reference_path']);references[meta['case_id']]=ref
 r=read(out/'runs'/filename(meta));verify_record(r,meta,plan('full')[meta['branch']],e,False)
 assert r['initial_head_digest']==ref['initial_head_digest'] and r['graph_sha256']==ref['graph_sha256']
 assert r['worker_ended_utc']>=r['worker_started_utc'] and r['engine_wall_seconds']>0
 assert r['worker_started_power']['ac_line_status']==r['worker_ended_power']['ac_line_status']==1
 if meta['branch']=='baseline':baseline_compare(r,ref)
 else:
  result=recovery(r);verdict.setdefault(meta['branch'],[]).append(dict(case_id=meta['case_id'],passed=result['passed']))
  for m in r['metrics']:
   if m['round'] in (160,180,200):
    for c in m['clients']:late.append(dict(case_id=meta['case_id'],branch=meta['branch'],round=m['round'],**c))
 for row in r['round_records']:
  for phase in ('private','generation','exchange','public'):
   values=[x[phase+'_seconds'] for x in r['round_records']];med=statistics.median(values)
   if row[phase+'_seconds']>max(2,10*med):warnings.append(dict(case_id=meta['case_id'],branch=meta['branch'],round=row['round'],phase=phase,seconds=row[phase+'_seconds']))
 completed.append((meta,r))
with tempfile.TemporaryDirectory(dir=H) as t:
 reports(Path(t),completed,references,fixture=False);generated=[]
 for p in Path(t).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
power=[json.loads(l) for p in out.glob('power_*.jsonl') for l in p.read_text(encoding='utf-8').splitlines()]
old=read(R/'experiments/quantity_heterogeneity/results_full/environment.json')['sources']
for p,h in old.items():assert sha(R/p)==h,p
result=dict(status='PASS',runs=len(completed),baseline40=4,long200=8,baseline_history_matched=4,caches_verified=4,source_files=len(env['sources']),completion_files=len(manifest['files']),old_sources_unchanged=len(old),reports_reproduced=sorted(generated),per_round_client_observations=sum(len(d['clients']) for m,r in completed for d in r['diagnostic_records']),verdict=verdict,late_test_records=late,power_samples=len(power),power_warnings=[p for p in power if p['gap_warning'] or p['ac_line_status']!=1],timing_flags=warnings,excluded_runs=0,excluded_rounds=0)
(H/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='late_test_records'}))
