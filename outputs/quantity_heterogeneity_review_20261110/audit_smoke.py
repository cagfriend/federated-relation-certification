from pathlib import Path
import sys,json,tempfile,csv
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R))
from experiments.quantity_heterogeneity.run import check_environment,verify_record,verify_groups,non_time_rows,_validate_equal_anchors
from experiments.quantity_heterogeneity.design import schedule,filename,input_key,plan,capacities
from experiments.quantity_heterogeneity.report import reports
from experiments.quantity_heterogeneity import data
from experiments.stl10_transfer.run import digest
H=Path(__file__).parent;out=H/'smoke_final'
def read(p):return json.loads(p.read_text(encoding='utf-8'))
env=read(out/'environment.json');check_environment(env)
manifest=read(out/'completed.json')
for name,h in manifest['files'].items():assert digest(out/name)==h,name
assert read(out/'finished.json')['completed_manifest_sha256']==digest(out/'completed.json')
normal=[];memory=[]
for mem,target in ((False,normal),(True,memory)):
 for meta in schedule('smoke',memory=mem):
  r=read(out/('memory' if mem else 'runs')/filename(meta));spec=plan('smoke')[meta['profile']]
  entry=env['inputs'][input_key(meta)]
  assert digest(Path(entry['path'])/'prepared.json')==entry['metadata_sha256']
  verify_record(r,meta,spec,entry['path'],mem,True);target.append((meta,r))
  if mem:
   ref=next(v for m,v in normal if all(meta[k]==m[k] for k in ('seed','partition','profile','method')))
   assert non_time_rows(r)==non_time_rows(ref)
   for f in ('persistent_method_array_bytes','initial_traffic','traffic'):assert r['summary'][meta['method']][f]==ref['summary'][meta['method']][f]
groups=verify_groups(normal)
for key,e in env['inputs'].items():
 seed,part,profile=key.split('|')
 data.verify(e['path'],plan('smoke')[profile],int(seed),part,profile=profile,fixture=True)
with tempfile.TemporaryDirectory(dir=H) as tmp:
 reports(Path(tmp),normal,memory,fixture=True);generated=[]
 for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
pairs=list(csv.DictReader((out/'paired_cost.csv').open(encoding='utf-8')))
for p in pairs:
 profile=p['regime'].replace('quantity_','');g=groups[(profile,p['partition'],int(p['seed']))];ref=p['comparison'][-1]
 assert float(p['head_ratio'])==g['D']['summary']['D']['head_pipeline_seconds']/g[ref]['summary'][ref]['head_pipeline_seconds']
anchors,anchor_sources=_validate_equal_anchors(R/'experiments/lr_client_scaling/results_full_fixed_per_client','full',False)
res=dict(status='PASS',formal_training_started=False,runs=len(normal),memory_runs=len(memory),groups=len(groups),reports_reproduced=sorted(generated),relations=sum(r['validation']['relation_comparisons'] for m,r in normal),candidates=sum(r['validation']['candidate_membership_comparisons'] for m,r in normal),mismatches=0,full_readonly_anchor_preflight=len(anchors),P3_pointers=len(anchor_sources['inputs']),sources=len(env['sources']),development_quality_trajectories=read(out/'scope.json')['quality_trajectories'])
(H/'audit.json').write_text(json.dumps(res,indent=2),encoding='utf-8');print(json.dumps(res))
