import sys,json,tempfile,hashlib,statistics,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));HERE=Path(__file__).parent
from experiments.public_scaling.data import sha
from experiments.public_scaling.util import load_json
from experiments.private_workload.run import check_environment,check_case,check_profile
from experiments.private_workload.design import spec_from_json
from experiments.private_workload.report import reports
from experiments.noniid_clustering.data import verify

def main():
 out=ROOT/'experiments/private_workload/results_full';done=load_json(out/'completed.json');env=load_json(out/'environment.json');check_environment(env)
 for name,h in done['files'].items():assert sha(out/name)==h,name
 cases=[];profiles=[];flags=[]
 for part in ('iid','dirichlet_0.1'):
  for seed in (404,505,606):
   marker=load_json(out/f'prepared_{part}_seed_{seed}.json');directory=Path(marker['path']);assert sha(directory/'prepared.json')==marker['metadata_sha256']
   verify(directory,spec_from_json(env['plan'][0]).config,seed,part)
   for s in map(spec_from_json,env['plan']):
    c=load_json(out/f'{part}_{s.case_id}_seed_{seed}.json');ref=None
    if s.private_limit is None:
     meta=env['references'][f'{part}_{seed}'];assert sha(Path(meta['path']))==meta['sha256'];ref=load_json(meta['path'])
    check_case(c,s,part,seed,env,directory,ref);cases.append(c)
    if s.private_limit is None:
     for m in ('B','E','D'):
      p=load_json(out/f'memory_{part}_{s.case_id}_{m}_seed_{seed}.json');check_profile(p,c,env);profiles.append({k:v for k,v in p.items() if k not in ('identity','payload_sha256')})
    for m in ('B','E','D'):
     rows=[r for r in c['round_records'] if r['method']==m]
     for k in rows[0]:
      if k.endswith('seconds') and isinstance(rows[0][k],(float,int)):
       med=statistics.median(r[k] for r in rows)
       for r in rows:
        if r[k]>max(1.,med*10):flags.append(dict(partition=part,seed=seed,case_id=s.case_id,method=m,round=r['round'],stage=k,seconds=r[k],median=med))
 ordered=[]
 for seed in (404,505,606):
  for part in ('iid','dirichlet_0.1'):
   specs=list(map(spec_from_json,env['plan']));shift=seed%3;specs=specs[shift:]+specs[:shift]
   for s in specs:ordered.append(next(c for c in cases if (c['seed'],c['partition'],c['case_id'])==(seed,part,s.case_id)))
 cases=ordered
 profiles.sort(key=lambda p:((404,505,606).index(p['seed']),('iid','dirichlet_0.1').index(p['partition']),('B','E','D').index(p['method'])))
 with tempfile.TemporaryDirectory(dir=HERE) as tmp:
  reports(Path(tmp),cases,profiles)
  for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name
 old=0
 for pkg in ('public_budget','noniid_clustering','collaboration_mechanism'):
  d=ROOT/f'experiments/{pkg}/results_full'
  for name,h in load_json(d/'completed.json')['files'].items():assert sha(d/name)==h;old+=1
 result=dict(completion={k:v for k,v in done.items() if k!='files'},verified_output_files=len(done['files']),regenerated_reports_byte_identical=True,prior_result_files_unchanged=old,timing_flags=flags)
 (HERE/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
