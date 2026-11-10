from pathlib import Path
import json,tempfile,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from experiments.lr_client_scaling.run import check_environment,verify_record,verify_groups,non_time_rows,input_key,spec_key
from experiments.lr_client_scaling.design import schedule,filename
from experiments.private_workload.design import spec_from_json
from experiments.lr_client_scaling.report import reports
from experiments.stl10_transfer.run import digest
from experiments.lr_repeat.run import sources as old_sources

ROOT=Path.cwd();dest=ROOT/'outputs/lr_client_scaling_review_20261109';out=dest/'smoke'
env=json.loads((out/'environment.json').read_text(encoding='utf-8'));check_environment(env)
manifest=json.loads((out/'completed.json').read_text(encoding='utf-8'))
for p,h in manifest['files'].items():assert digest(out/p)==h,p
assert json.loads((out/'finished.json').read_text(encoding='utf-8'))['completed_manifest_sha256']==digest(out/'completed.json')
normal=[];memory=[]
for mem,target in ((False,normal),(True,memory)):
 for meta in schedule('smoke',memory=mem):
  r=json.loads((out/('memory' if mem else 'runs')/filename(meta)).read_text(encoding='utf-8'))
  marker=json.loads((out/'inputs'/(input_key(meta).replace('|','_')+'.json')).read_text(encoding='utf-8'))
  spec=spec_from_json(env['plan'][spec_key(meta)])
  verify_record(r,meta,spec,marker['path'],mem,True);target.append((meta,r))
  if mem:
   ref=next(r for m,r in normal if all(meta[k]==m[k] for k in ('seed','partition','clients','method','regime')))
   assert non_time_rows(r)==non_time_rows(ref)
groups=verify_groups(normal)
with tempfile.TemporaryDirectory(dir=dest) as t:
 reports(Path(t),normal,memory,fixture=True);generated=[]
 for p in Path(t).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
old=json.loads((ROOT/'experiments/lr_repeat/results_full/environment.json').read_text(encoding='utf-8'))['sources']
assert old_sources()==old
result=dict(status='PASS',formal_training_started=False,runs=len(normal),memory_runs=len(memory),triples=len(groups),relations=sum(r['validation']['relation_comparisons'] for m,r in normal),candidates=sum(r['validation']['candidate_membership_comparisons'] for m,r in normal),mismatches=0,reports_reproduced=generated,previous_frozen_sources_unchanged=len(old),frozen_sources=len(env['sources']))
(dest/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
