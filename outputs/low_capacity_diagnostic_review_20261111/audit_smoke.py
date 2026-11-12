from pathlib import Path
import sys,json,tempfile,hashlib
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R))
from experiments.low_capacity_diagnostic.run import check_environment,verify_record,baseline_compare,read
from experiments.low_capacity_diagnostic.design import plan,schedule,filename
from experiments.low_capacity_diagnostic.report import reports
H=Path(__file__).parent;out=H/'smoke_final_v2';env=read(out/'environment.json');check_environment(env)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(out/'completed.json')
for name,h in manifest['files'].items():assert sha(out/name)==h,name
assert read(out/'finished.json')['completed_manifest_sha256']==sha(out/'completed.json')
references={};completed=[]
for meta in schedule('smoke'):
 entry=env['inputs'][meta['case_id']];ref=read(entry['reference_path']);references[meta['case_id']]=ref
 assert sha(Path(entry['path'])/'prepared.json')==entry['metadata_sha256']
 assert sha(Path(entry['reference_path']))==entry['reference_sha256']
 r=read(out/'runs'/filename(meta));verify_record(r,meta,plan('smoke')[meta['branch']],entry,True)
 if meta['branch']=='baseline':baseline_compare(r,ref)
 completed.append((meta,r))
with tempfile.TemporaryDirectory(dir=H) as t:
 reports(Path(t),completed,references,fixture=True);generated=[]
 for p in Path(t).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;generated.append(p.name)
formal=read(H/'formal_input_preflight.json');assert formal['formal_training_started'] is False and len(formal['cases'])==4
old=read(R/'experiments/quantity_heterogeneity/results_full/environment.json')['sources']
for p,h in old.items():assert sha(R/p)==h,p
result=dict(status='PASS',formal_training_started=False,runs=len(completed),short_baselines=sum(m['branch']=='baseline' for m,r in completed),per_round_clients_observed=sum(len(x['clients']) for m,r in completed for x in r['diagnostic_records']),reports_reproduced=sorted(generated),frozen_sources=len(env['sources']),old_frozen_sources_unchanged=len(old),formal_cache_preflight=4,readonly_observations_match_frozen_baseline=True,private_only_public_updates=0)
(H/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
