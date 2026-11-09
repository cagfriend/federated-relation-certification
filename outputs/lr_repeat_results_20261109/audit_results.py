from pathlib import Path
import sys,json,csv,statistics,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from experiments.lr_repeat.run import read,check_environment,validate,compare_method,anchor_for,verify_blocks
from experiments.lr_repeat.design import plan,schedule,filename,criteria
from experiments.lr_repeat.report import reports
from experiments.stl10_transfer.run import digest

ROOT=Path(__file__).resolve().parents[2]
out=ROOT/'experiments/lr_repeat/results_full';dest=Path(__file__).parent
env=read(out/'environment.json');check_environment(env)
manifest=read(out/'completed.json')
for name,h in manifest['files'].items():assert digest(out/name)==h,name
assert read(out/'finished.json')['completed_manifest_sha256']==digest(out/'completed.json')
completed=[];flags=[]
for meta in schedule('full'):
 r=read(out/'runs'/filename(meta));spec=plan('full')[meta['case_id']]
 validate(r,meta,spec,env['inputs'][meta['case_id']]['entry'],False)
 compare_method(r,anchor_for(env,meta));completed.append((meta,r))
 assert r['worker_started_power']['ac_line_status']==r['worker_ended_power']['ac_line_status']==1
 for phase in ('private','generation','exchange','public','pipeline'):
  rows=r['round_records'][1:] if phase in ('generation','pipeline') else r['round_records']
  med=statistics.median(x[phase+'_seconds'] for x in rows)
  for row in rows:
   if row[phase+'_seconds']>max(2,10*med):flags.append(dict(case_id=meta['case_id'],method=meta['method'],repeat=meta['repeat'],round=row['round'],phase=phase,seconds=row[phase+'_seconds'],median=med))
verify_blocks(completed)
assert len(list((out/'runs').glob('*.json')))==len(completed)==36
with tempfile.TemporaryDirectory(dir=dest) as tmp:
 reports(Path(tmp),completed,fixture=False);generated=[]
 for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
summary=[]
for cid in plan('full'):
 pairs=[]
 for repeat in range(3):
  rows={m['method']:r for m,r in completed if m['case_id']==cid and m['repeat']==repeat}
  h={method:r['summary'][method]['head_pipeline_seconds'] for method,r in rows.items()}
  pairs.append(dict(repeat=repeat,D_B=h['D']/h['B'],D_E=h['D']/h['E']))
 b=[x['D_B'] for x in pairs];e=[x['D_E'] for x in pairs]
 summary.append(dict(case_id=cid,pairs=pairs,D_B_saving_pct=100*(1-statistics.median(b)),D_E_saving_pct=100*(1-statistics.median(e)),criteria=criteria(b,e)))
power=[json.loads(l) for p in out.glob('power_*.jsonl') for l in p.read_text().splitlines()]
warnings=[r for r in power if r['gap_warning'] or r['ac_line_status']!=1]
result=dict(status='PASS',runs=36,cases=4,rounds_per_run=200,sources=len(env['sources']),manifest_files=len(manifest['files']),reports_reproduced=sorted(generated),relations=sum(r['validation']['relation_comparisons'] for m,r in completed),candidates=sum(r['validation']['candidate_membership_comparisons'] for m,r in completed),mismatches=0,all_P1_method_anchors_matched=True,power_samples=len(power),power_warnings=warnings,max_sample_gap_seconds=max(r['sample_gap_seconds'] or 0 for r in power),timing_flags=flags,excluded_runs=0,excluded_rounds=0,case_statistics=summary)
(dest/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
