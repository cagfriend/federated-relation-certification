"""One diagnostic rerun of the previously slow triple; no replacement statistics."""
import sys,json,time,subprocess,shutil
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R));O=Path(__file__).parent;OLD=R/'experiments/perf_confirmation/results_full'
from experiments.public_scaling.util import load_json,seal_payload
from experiments.public_scaling.data import sha
from experiments.perf_confirmation.run import check_environment,check_run,save
from experiments.perf_confirmation.design import schedule,run_filename,spec_from_json
from experiments.perf_confirmation.engine import method_signature,trajectory_signature
env=load_json(OLD/'environment.json');check_environment(env)
metas=[m for m in schedule('full') if (m['partition'],m['seed'],m['case_id'],m['repeat'])==('dirichlet_0.1',909,'m16384_fixed8_priv2048',1)]
assert len(metas)==3
before={p.relative_to(OLD).as_posix():sha(p) for p in OLD.rglob('*') if p.is_file()}
(O/'runs').mkdir(exist_ok=True)
for name in ('environment.json','prepared_dirichlet_0.1_seed_909.json'):
 dest=O/name
 if dest.exists():assert dest.read_bytes()==(OLD/name).read_bytes()
 else:shutil.copyfile(OLD/name,dest)
directory=Path(load_json(O/'prepared_dirichlet_0.1_seed_909.json')['path']);spec=next(spec_from_json(s) for s in env['plan'] if spec_from_json(s).case_id==metas[0]['case_id']);runs=[];comparison=[]
for meta in metas:
 target=O/'runs'/run_filename(meta)
 if target.exists():r=load_json(target)
 else:
  print('Diagnostic rerun: '+meta['method']+' original position='+str(meta['position']),flush=True)
  cmd=[sys.executable,'-m','experiments.perf_confirmation.run','--output',str(O),'--worker-run','--worker-partition',meta['partition'],'--worker-seed','909','--worker-case',meta['case_id'],'--worker-method',meta['method'],'--worker-repeat','1']
  start=time.perf_counter();p=subprocess.run(cmd,cwd=R,capture_output=True,text=True);wall=time.perf_counter()-start
  if p.returncode:raise RuntimeError(p.stderr)
  info=json.loads(p.stdout.strip().splitlines()[-1]);pending=O/'runs'/('pending_'+run_filename(meta));r=load_json(pending)
  r.update(partition=meta['partition'],triple=meta['triple'],position=meta['position'],repeat=1,identity=env,process_wall_seconds=wall,process_peak_bytes=info['process_peak_bytes']);r=seal_payload(r)
  check_run(r,spec,meta['partition'],909,env,directory,meta);save(target,r);pending.unlink()
 check_run(r,spec,meta['partition'],909,env,directory,meta)
 original=load_json(OLD/'runs'/run_filename(meta));assert method_signature(r)==method_signature(original)
 row=dict(method=meta['method'],rerun_head_seconds=r['summary'][meta['method']]['head_pipeline_seconds'])
 for rep in (0,1):
  prev=load_json(OLD/'runs'/run_filename(dict(meta,repeat=rep)));row['original_rep'+str(rep)+'_head_seconds']=prev['summary'][meta['method']]['head_pipeline_seconds']
 comparison.append(row);runs.append(r);print(json.dumps(row),flush=True)
assert all(trajectory_signature(r)==trajectory_signature(runs[0]) for r in runs)
assert before=={p.relative_to(OLD).as_posix():sha(p) for p in OLD.rglob('*') if p.is_file()}
result=dict(diagnostic_only=True,original_results_unchanged=True,all_method_signatures_identical_to_original=True,comparison=comparison,files={p.relative_to(O).as_posix():sha(p) for p in O.rglob('*') if p.is_file() and p.name!='completed.json'})
save(O/'completed.json',result)
print('Finished diagnostic triple rerun',flush=True)
