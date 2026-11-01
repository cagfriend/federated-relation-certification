"""Frozen STL-10 transfer runner. Each method is executed in its own process."""
import argparse, hashlib, json, math, os, re, subprocess, sys, time
from pathlib import Path
from threadpoolctl import threadpool_limits
from experiments.public_scaling.data import runtime as core_runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.private_workload.design import spec_from_json
from experiments.noniid_clustering.data import partition_indices
from . import data
from .design import METHODS, PARTITIONS, plan, schedule, filename
from .engine import run as engine_run
from .report import reports

ROOT=Path(__file__).resolve().parents[2]
DIR=Path(__file__).parent
def digest(p):
 h=hashlib.sha256();
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def files_hash(paths): return {str(Path(p).resolve()):digest(p) for p in paths}
def frozen_sources():
 folders=['stl10_transfer','public_scaling','private_workload','public_budget','noniid_clustering']
 out={}
 for folder in folders:
  for p in sorted((ROOT/'experiments'/folder).glob('*.py')): out[str(p.relative_to(ROOT))]=digest(p)
 out['experiments/stl10_transfer/PREREGISTRATION.md']=digest(DIR/'PREREGISTRATION.md')
 return out
def power_status():
 if os.name!='nt': return {'verified':False,'ac_line_status':None,'scheme':None,'reason':'non-Windows platform'}
 import ctypes
 class P(ctypes.Structure): _fields_=[('ACLineStatus',ctypes.c_byte),('BatteryFlag',ctypes.c_byte),('BatteryLifePercent',ctypes.c_byte),('Reserved1',ctypes.c_byte),('BatteryLifeTime',ctypes.c_ulong),('BatteryFullLifeTime',ctypes.c_ulong)]
 x=P(); ok=bool(ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(x)))
 try:
  raw=subprocess.check_output(['powercfg','/getactivescheme'],stderr=subprocess.STDOUT)
  line=raw.decode('utf-8',errors='replace').strip(); match=re.search(r'[0-9a-fA-F-]{36}',line); scheme={'guid':match.group(0) if match else None,'description':line}
 except Exception as e: scheme=f'unavailable: {e}'
 return {'verified':ok,'ac_line_status':int(x.ACLineStatus) if ok else None,'scheme':scheme}
def write_new(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 t=p.with_suffix(p.suffix+'.part');t.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');t.replace(p)
def check_environment(e):
 if e['source_hashes']!=frozen_sources(): raise ValueError('Frozen source changed')
 now=core_runtime()
 if any(e['runtime'].get(k)!=now.get(k) for k in ('python','executable','numpy','scipy','sklearn','torch','platform')): raise ValueError('Runtime changed')
 if e['plan']!=[s.json() for s in plan(e['preset'],e['prepare_device'])]: raise ValueError('Frozen plan changed')
def check_run(r,meta,spec,prepared,fixture):
 if r.get('run_sha256')!=hashlib.sha256(json.dumps({k:v for k,v in r.items() if k!='run_sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest(): raise ValueError('Run seal mismatch')
 for k,v in [('seed',meta['seed']),('partition',meta['partition']),('method',meta['method']),('case_id',meta['case_id']),('dataset','STL-10 fixture' if fixture else 'STL-10')]:
  if r.get(k)!=v: raise ValueError(f'Run identity mismatch: {k}')
 if r['spec']!=spec.json() or r['config']!=spec.config.json() or r['case_id']!=spec.case_id or r['prepared_directory']!=str(prepared.resolve()): raise ValueError('Run spec/cache mismatch')
 cfg=spec.config; rr=r['round_records']; n=len(cfg.dimensions); e=cfg.samples*cfg.degree//2
 if [x['round'] for x in rr]!=list(range(1,cfg.rounds+1)): raise ValueError('Incomplete round coverage')
 if any(x['method']!=meta['method'] for x in rr): raise ValueError('Round method differs')
 for x in rr:
  for phase in ('private','generation','exchange','public','pipeline'):
   if not math.isfinite(x[phase+'_seconds']) or x[phase+'_seconds']<0: raise ValueError('Invalid timing')
 s=r['summary'][meta['method']]
 if abs(s['head_pipeline_seconds']-(s['initialization_seconds']+sum(x['pipeline_seconds'] for x in rr)))>1e-8: raise ValueError('Head pipeline summary mismatch')
 for phase in ('private','generation','exchange','public'):
  if abs(s[phase+'_seconds']-sum(x[phase+'_seconds'] for x in rr))>1e-8: raise ValueError('Phase summary mismatch')
 if s['final_head_digest']!=rr[-1]['head_digest_after_public']: raise ValueError('Final digest differs')
 if s['final_metrics']!=r['metrics'][-1] or r['metrics'][-1]['round']!=cfg.rounds: raise ValueError('Final metrics differ')
 v=r['validation']; expected=0 if meta['method']=='B' else cfg.rounds*n*cfg.samples
 if not v['enabled'] or v['mismatches'] or v['relation_comparisons']!=cfg.rounds*n*e or v['candidate_membership_comparisons']!=expected: raise ValueError('Oracle coverage mismatch')
 if not r['coverage_records'] or len(r['coverage_records'])!=cfg.rounds: raise ValueError('Coverage records incomplete')
 return True
def seal(r): r.pop('run_sha256',None);r['run_sha256']=hashlib.sha256(json.dumps(r,sort_keys=True,separators=(',',':')).encode()).hexdigest();return r

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--preset',choices=('full','smoke'),default='full');ap.add_argument('--prepare-device',choices=('cpu','cuda'));ap.add_argument('--download',action='store_true');ap.add_argument('--resume',action='store_true');ap.add_argument('--output',type=Path);ap.add_argument('--cache',type=Path,default=DIR/'prepared');ap.add_argument('--data-dir',type=Path,default=DIR/'data');ap.add_argument('--worker',action='store_true',help=argparse.SUPPRESS);ap.add_argument('--worker-seed',type=int,help=argparse.SUPPRESS);ap.add_argument('--worker-partition',choices=PARTITIONS,help=argparse.SUPPRESS);ap.add_argument('--worker-case',help=argparse.SUPPRESS);ap.add_argument('--worker-method',choices=METHODS,help=argparse.SUPPRESS)
 a=ap.parse_args();out=(a.output or DIR/f'results_{a.preset}').resolve();runs=out/'runs'
 if a.worker:
  env=json.loads((out/'environment.json').read_text(encoding='utf-8'));check_environment(env);spec=next(spec_from_json(x) for x in env['plan'] if spec_from_json(x).case_id==a.worker_case);marker=json.loads((out/f"prepared_{a.worker_partition}_seed_{a.worker_seed}.json").read_text(encoding='utf-8'));prep=Path(marker['path']);
  if digest(prep/'prepared.json')!=marker['metadata_sha256']: raise ValueError('Prepared metadata changed')
  data.verify(prep,spec.config,a.worker_seed,a.worker_partition,fixture=env['fixture'])
  t=time.perf_counter()
  with threadpool_limits(limits=spec.config.threads): r=engine_run(prep,spec,a.worker_method,fixture=env['fixture'])
  r.update(seed=a.worker_seed,partition=a.worker_partition,method=a.worker_method,worker_wall_seconds=time.perf_counter()-t,process_peak_bytes=native_peak_bytes());r=seal(r);check_run(r,dict(seed=a.worker_seed,partition=a.worker_partition,method=a.worker_method,case_id=spec.case_id),spec,prep,env['fixture']);write_new(runs/filename(dict(seed=a.worker_seed,partition=a.worker_partition,method=a.worker_method,case_id=spec.case_id)),r);return
 if a.resume:
  env=json.loads((out/'environment.json').read_text(encoding='utf-8'));check_environment(env);a.cache=Path(env['cache']);a.data_dir=Path(env['data_dir'])
 else:
  if out.exists() and any(out.iterdir()): raise FileExistsError('Output exists; use --resume or a new --output')
  specs=plan(a.preset,a.prepare_device);env=dict(preset=a.preset,prepare_device=specs[0].config.prepare_device,plan=[s.json() for s in specs],fixture=a.preset=='smoke',cache=str(a.cache.resolve()),data_dir=str(a.data_dir.resolve()),runtime=core_runtime(),source_hashes=frozen_sources(),started_power=power_status(),started_utc=time.time(),execution='one method per independent process, serial')
  if a.preset=='full' and env['started_power']['ac_line_status']!=1: raise RuntimeError('Full run requires verified ACLineStatus=1 at start')
  out.mkdir(parents=True,exist_ok=True);runs.mkdir(exist_ok=True);write_new(out/'environment.json',env)
 specs=[spec_from_json(x) for x in env['plan']]
 invocation_power=power_status()
 if env['preset']=='full' and invocation_power['ac_line_status']!=1: raise RuntimeError('Full run and resume require verified ACLineStatus=1')
 write_new(out/f'invocation_{time.time_ns()}.json',dict(utc=time.time(),resume=a.resume,power=invocation_power))
 # Shared maximum public pool: prepare once per seed/partition using the larger M spec.
 prepared={}
 for seed in (1001,1002,1003) if env['preset']=='full' else (1001,):
  for part in PARTITIONS:
   marker=out/f'prepared_{part}_seed_{seed}.json'
   if marker.exists():
    m=json.loads(marker.read_text(encoding='utf-8'));p=Path(m['path'])
    if digest(p/'prepared.json')!=m['metadata_sha256']: raise ValueError('Prepared metadata changed')
   else:
    p=data.prepare(a.cache,a.data_dir,specs[-1].config,seed,part,download=a.download and not env['fixture'],fixture=env['fixture'])
    write_new(marker,dict(path=str(p.resolve()),metadata_sha256=digest(p/'prepared.json')))
   data.verify(p,specs[-1].config,seed,part,fixture=env['fixture']);prepared[seed,part]=p
 completed_runs=[]
 for meta in schedule(env['preset']):
  spec=next(s for s in specs if s.case_id==meta['case_id']);p=prepared[meta['seed'],meta['partition']];target=runs/filename(meta)
  if target.exists():
   r=json.loads(target.read_text(encoding='utf-8'));check_run(r,meta,spec,p,env['fixture']);completed_runs.append((meta,r));print('Preserved: '+target.name,flush=True);continue
  print('Running: '+target.name,flush=True)
  cmd=[sys.executable,'-m','experiments.stl10_transfer.run','--output',str(out),'--worker','--worker-seed',str(meta['seed']),'--worker-partition',meta['partition'],'--worker-case',meta['case_id'],'--worker-method',meta['method']]
  subprocess.run(cmd,check=True)
  r=json.loads(target.read_text(encoding='utf-8'));check_run(r,meta,spec,p,env['fixture']);completed_runs.append((meta,r))
 expected_schedule=schedule(env['preset'])
 if len(completed_runs)!=len(expected_schedule): raise ValueError('Expected run matrix is incomplete')
 expected_names={filename(m) for m in expected_schedule}
 if {p.name for p in runs.glob('*.json')}!=expected_names: raise ValueError('Unexpected or missing run files')
 rs=[r for _,r in completed_runs]
 trajectory_keys=('head_digest_after_public','public_schedule_digest','public_optimizer_steps','student_forward_endpoints','public_edges_consumed','committed_counts_digest','received_counts_digests','private_loss','public_loss','private_subset_digest','private_samples_per_client','private_subset_pseudo_histograms','private_optimizer_steps','private_forward_endpoints','positive_relation_fraction','traffic')
 triples={}
 for meta,r in completed_runs: triples.setdefault((meta['partition'],meta['seed'],meta['case_id']),{})[meta['method']]=r
 for key,group in triples.items():
  if set(group)!=set(METHODS): raise ValueError(f'Incomplete method triple: {key}')
  base=group['B']
  for method in ('E','D'):
   other=group[method]
   if other['initial_head_digest']!=base['initial_head_digest'] or other['graph_sha256']!=base['graph_sha256']: raise ValueError('Initial state or graph differs across methods')
   if [{k:x[k] for k in trajectory_keys} for x in other['round_records']] != [{k:x[k] for k in trajectory_keys} for x in base['round_records']]: raise ValueError(f'Trajectory mismatch in {key}')
   if [{k:v for k,v in q.items() if k!='method'} for q in other['metrics']] != [{k:v for k,v in q.items() if k!='method'} for q in base['metrics']]: raise ValueError('Quality metrics differ across methods')
 # Across M, hold initial heads and private workload fixed; public graph targets may differ.
 b_runs={(m['partition'],m['seed'],m['case_id']):r for m,r in completed_runs if m['method']=='B'}
 for part in PARTITIONS:
  for seed in (1001,1002,1003) if env['preset']=='full' else (1001,):
   pairs=[(c,r) for (p,s,c),r in b_runs.items() if p==part and s==seed]
   if len(pairs)==2:
    x,y=pairs
    if x[1]['initial_head_digest']!=y[1]['initial_head_digest']: raise ValueError('Initial heads differ across M')
    for f in ('private_subset_digest','private_samples_per_client','private_subset_pseudo_histograms'):
     if [v[f] for v in x[1]['round_records']] != [v[f] for v in y[1]['round_records']]: raise ValueError('Private workload differs across M')
 reports(out,rs,fixture=env['fixture'],preset=env['preset'])
 check_environment(env)
 env['ended_power']=power_status();env['ended_utc']=time.time();env['power_monitoring']='start/end snapshots only; intermediate changes are unobserved';write_new(out/'environment_final.json',env)
 manifest={str(x.relative_to(out)):digest(x) for x in sorted(out.rglob('*')) if x.is_file() and x.name not in ('completed.json','finished.json')}
 write_new(out/'completed.json',dict(files=manifest,count=len(rs),blocks_verified=len(triples),mismatches=0,relation_comparisons=sum(r['validation']['relation_comparisons'] for r in rs),candidate_membership_comparisons=sum(r['validation']['candidate_membership_comparisons'] for r in rs),finished_utc=env['ended_utc']))
 write_new(out/'finished.json',dict(status='complete',expected_runs=len(expected_schedule),completed_runs=len(rs),completed_manifest_sha256=digest(out/'completed.json')))
 print('Finished: '+str(out/'report.md'),flush=True)
if __name__=='__main__': main()
