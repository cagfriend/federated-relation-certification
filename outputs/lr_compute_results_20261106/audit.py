from pathlib import Path
import sys,json,csv,tempfile,statistics
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from experiments.lr_compute.run import read,check_environment,validate,input_for,compare_anchor,groups_check,non_time_rows
from experiments.lr_compute.design import plan,schedule,filename
from experiments.lr_compute.report import reports
from experiments.stl10_transfer.run import digest
out=Path('experiments/lr_compute/results_full');dest=Path('outputs/lr_compute_results_20261106');env=read(out/'environment.json');check_environment(env)
manifest=read(out/'completed.json')
for name,value in manifest['files'].items():assert digest(out/name)==value,name
assert read(out/'finished.json')['completed_manifest_sha256']==digest(out/'completed.json')
completed=[];memories=[];flags=[];anchors=0
for memory in (False,True):
 for meta in schedule('full',memory):
  r=read(out/('memory' if memory else 'runs')/filename(meta));spec=plan('full')[meta['case_id']];item=input_for(env,meta['case_id']);entry=item['entry']
  assert digest(Path(entry['base_directory'])/'prepared.json')==entry['base_metadata_sha256']
  if 'k_directory' in entry:assert digest(Path(entry['k_directory'])/'prepared_k.json')==entry['k_metadata_sha256']
  validate(r,meta,spec,entry,memory,False)
  if memory:
   reference=next(z for m,z in completed if m['case_id']==meta['case_id'] and m['method']==meta['method'])
   assert non_time_rows(r)==non_time_rows(reference)
   assert r['initial_head_digest']==reference['initial_head_digest']
   assert r['summary'][meta['method']]['persistent_method_array_bytes']==reference['summary'][meta['method']]['persistent_method_array_bytes']
   memories.append((meta,r))
  else:
   compare_anchor(r,read(item['anchor'])['result']);anchors+=1;completed.append((meta,r))
  if not memory:
   for phase in ('private','generation','exchange','public','pipeline'):
    rows=r['round_records'][1:] if phase in ('generation','pipeline') else r['round_records'];med=statistics.median(x[phase+'_seconds'] for x in rows)
    for row in rows:
     if row[phase+'_seconds']>max(2,10*med):flags.append(dict(case_id=meta['case_id'],method=meta['method'],round=row['round'],phase=phase,seconds=row[phase+'_seconds'],median=med))
groups=groups_check(completed)
with tempfile.TemporaryDirectory(dir=dest) as tmp:
 reports(Path(tmp),completed,memories,fixture=False);generated=[]
 for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
pairs=list(csv.DictReader((out/'paired_cost.csv').open(encoding='utf-8')));family_summary=[]
for family in ('n12_k10','n6_k64'):
 for comparison in ('D/B','D/E'):
  values=[p for p in pairs if p['family']==family and p['comparison']==comparison];ratios=[float(p['head_ratio']) for p in values]
  family_summary.append(dict(family=family,comparison=comparison,cases=len(values),median_head_saving_pct=100*(1-statistics.median(ratios)),min_head_saving_pct=100*(1-max(ratios)),max_head_saving_pct=100*(1-min(ratios)),wins=sum(x<1 for x in ratios)))
for row in pairs:
 meta=next(m for m,r in completed if m['case_id']==row['case_id'] and m['method']=='D');g=groups[meta['case_id']];ref=row['comparison'][-1]
 assert float(row['head_ratio'])==g['D']['summary']['D']['head_pipeline_seconds']/g[ref]['summary'][ref]['head_pipeline_seconds']
assert sum(p['total_ratio']=='' for p in pairs)==2
quality=list(csv.DictReader((out/'quality.csv').open(encoding='utf-8')));assert all(q['passed']=='True' and q['final_near99_clients']=='0' and q['final_single_clients']=='0' for q in quality)
power=[json.loads(line) for p in out.glob('power_*.jsonl') for line in p.read_text(encoding='utf-8').splitlines()];warnings=[p for p in power if p['gap_warning'] or p['ac_line_status']!=1]
r=dict(status='PASS',runs=len(completed),memory_runs=len(memories),triples=len(groups),anchor_runs_matched=anchors,manifest_files=len(manifest['files']),sources=len(env['sources']),reports_reproduced=generated,relations=sum(r['validation']['relation_comparisons'] for m,r in completed),candidates=sum(r['validation']['candidate_membership_comparisons'] for m,r in completed),mismatches=0,quality_all_passed=True,masked_preparation_pairs=2,family_summary=family_summary,power_samples=len(power),power_warnings=warnings,timing_flags=flags,excluded_runs=0,excluded_rounds=0)
(dest/'audit.json').write_text(json.dumps(r,indent=2),encoding='utf-8');print(json.dumps(r))
