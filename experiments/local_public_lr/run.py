"""Matched full baseline and local public-LR intervention with read-only probes."""
from pathlib import Path
import argparse,json,time,sys,subprocess
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.data import runtime
from experiments.stl10_transfer.run import digest,seal,write_new,power_status
from experiments.client_scaling.telemetry import Monitor
from experiments.quantity_heterogeneity import run as old_run,data as old_data,engine as old_engine
from .design import plan,cases,schedule,filename,source_key,PROBE_SIZES,PROBE_STREAM,PLAN_COMMIT,public_client_weights
from experiments.low_capacity_diagnostic import run as diagnostic_run
from .probes import manifest as probe_manifest
from .engine import run as engine_run
from .report import reports
ROOT=Path(__file__).resolve().parents[2];DIR=Path(__file__).parent


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def sources():
    result=diagnostic_run.sources()
    for p in DIR.glob('*.py'):result[str(p.relative_to(ROOT))]=digest(p)
    result[str((DIR/'PREREGISTRATION.md').relative_to(ROOT))]=digest(DIR/'PREREGISTRATION.md')
    return result


def check_environment(env):
    if env['sources']!=sources():raise ValueError('Frozen sources changed')
    now=runtime()
    for k in ('python','executable','numpy','scipy','sklearn','torch','platform'):
        if now[k]!=env['runtime'][k]:raise ValueError('Runtime changed: '+k)
    if env['plan']!={b:s.json() for b,s in plan(env['preset']).items()} or env['schedule']!=schedule(env['preset']):raise ValueError('Frozen plan/schedule changed')
    if env['probe_config']!=dict(stream=PROBE_STREAM,size=PROBE_SIZES[env['preset']],selection='sorted local choice without replacement'):raise ValueError('Probe configuration changed')
    if env['plan_commit']!=PLAN_COMMIT:raise ValueError('Plan version changed')
    if env['public_client_weights']!={b:public_client_weights(b) for b in plan(env['preset'])}:raise ValueError('Frozen client weights changed')


def source_snapshot(root):
    env=read(root/'environment.json');old_run.check_environment(env)
    completed=read(root/'completed.json')
    for name,h in completed['files'].items():
        if digest(root/name)!=h:raise ValueError('Historical source changed: '+name)
    if read(root/'finished.json')['completed_manifest_sha256']!=digest(root/'completed.json'):raise ValueError('Historical finished seal mismatch')
    return dict(environment=digest(root/'environment.json'),completed=digest(root/'completed.json'),finished=digest(root/'finished.json'))


def baseline_compare(record,reference):
    if record['initial_head_digest']!=reference['initial_head_digest'] or record['graph_sha256']!=reference['graph_sha256']:raise ValueError('Historical initial state/graph mismatch')
    n=record['config']['rounds'];old=reference['round_records'][:n]
    if len(old)!=n:raise ValueError('Insufficient historical rounds')
    strip=lambda rows:[{k:v for k,v in r.items() if not k.endswith('_seconds')} for r in rows]
    if strip(record['round_records'])!=strip(old):raise ValueError('Historical training trajectory mismatch')
    metrics={m['round']:m for m in reference['metrics']}
    if any(m!=metrics.get(m['round']) for m in record['metrics']):raise ValueError('Historical checkpoint mismatch')


def verify_record(r,meta,spec,entry,fixture):
    diagnostic_run.verify_record(r,meta,spec,entry,fixture)
    weights=public_client_weights(meta['branch'])
    if r.get('public_client_weights')!=weights:raise ValueError('Public client weights mismatch')
    for d in [r['initial_diagnostics']]+r['diagnostic_records']:
        if [c.get('actual_public_weight') for c in d['clients']]!=weights:
            raise ValueError('Actual per-client public weight mismatch')
        if [c.get('actual_public_effective_lr') for c in d['clients']]!=[spec.config.head_lr*w for w in weights]:
            raise ValueError('Actual per-client effective public LR mismatch')


def diagnostic_snapshot(root):
    env=read(root/'environment.json');diagnostic_run.check_environment(env)
    completed=read(root/'completed.json')
    for name,h in completed['files'].items():
        if digest(root/name)!=h:raise ValueError('Diagnostic history changed: '+name)
    if read(root/'finished.json')['completed_manifest_sha256']!=digest(root/'completed.json'):raise ValueError('Diagnostic finished seal mismatch')
    return dict(environment=digest(root/'environment.json'),completed=digest(root/'completed.json'),finished=digest(root/'finished.json'))


def prepare_history(env,out):
    if env['fixture']:return {}
    root=Path(env['diagnostic_results']);snap=diagnostic_snapshot(root)
    if env.get('diagnostic_snapshot') not in (None,snap):raise ValueError('Diagnostic source identity changed')
    env['diagnostic_snapshot']=snap
    prior_env=read(root/'environment.json');case=cases(env['preset'])[0];cid=case['case_id']
    item=env['inputs'][cid];old_item=prior_env['inputs'][cid]
    if any(item[k]!=old_item[k] for k in ('path','metadata_sha256','probe_manifest')):raise ValueError('Historical diagnostic input/probe mismatch')
    history={};files={}
    for branch in ('private_only','low_lr'):
        meta=dict(case,branch=branch);path=root/'runs'/diagnostic_run.filename(meta);r=read(path)
        diagnostic_run.verify_record(r,meta,diagnostic_run.plan('full')[branch],old_item,False)
        reference=read(item['reference_path'])
        if any(r[k]!=reference[k] for k in ('initial_head_digest','graph_sha256')):raise ValueError('Historical diagnostic initial state mismatch')
        files[branch]=dict(path=str(path.resolve()),sha256=digest(path));history[branch]=r
    if env.get('historical_diagnostics') not in (None,files):raise ValueError('Historical diagnostic records changed')
    env['historical_diagnostics']=files;write_new(out/'environment.json',env)
    return history


def prepare_inputs(env,out):
    inputs=env.get('inputs',{});refs={};preset=env['preset'];fixture=env['fixture']
    source=Path(env['source_results'])
    if not fixture:
        snap=source_snapshot(source)
        if env.get('source_snapshot') not in (None,snap):raise ValueError('Historical source identity changed')
        env['source_snapshot']=snap;old_env=read(source/'environment.json')
    for case in cases(preset):
        cid=case['case_id'];spec=plan(preset)['baseline']
        if cid in inputs:
            item=inputs[cid];path=Path(item['path'])
            if digest(path/'prepared.json')!=item['metadata_sha256']:raise ValueError('Input metadata changed')
        elif fixture:
            print('Preparing synthetic input: '+cid,flush=True)
            path=old_data.prepare(env['cache'],DIR/'fixture_data',spec,case['seed'],case['partition'],profile='strong',fixture=True)
            item=dict(path=str(path.resolve()),metadata_sha256=digest(path/'prepared.json'))
        else:
            item=dict(old_env['inputs'][source_key(case)]);path=Path(item['path'])
        if digest(path/'prepared.json')!=item['metadata_sha256']:raise ValueError('Input metadata digest mismatch')
        old_data.verify(path,spec,case['seed'],case['partition'],profile='strong',fixture=fixture)
        public=np.load(path/'public_ids.npy',allow_pickle=False)[:spec.config.samples]
        probe=probe_manifest(case['seed'],public,PROBE_SIZES[preset])
        if 'probe_manifest' in item and item['probe_manifest']!=probe:raise ValueError('Probe selection drift')
        item['probe_manifest']=probe
        if fixture:
            target=Path(item['reference_path']) if 'reference_path' in item else out/'references'/(cid+'.json')
            if 'reference_path' in item and not target.exists():raise FileNotFoundError('Frozen synthetic reference is missing: '+str(target))
            if not target.exists():
                with threadpool_limits(limits=1):reference=old_engine.run(path,spec,'B',profile='strong',fixture=True,progress=False)
                write_new(target,seal(reference))
        else:target=source/'runs'/f"{case['partition']}_strong_seed{case['seed']}_B.json"
        if item.get('reference_sha256',digest(target))!=digest(target):raise ValueError('Historical reference changed')
        reference=read(target)
        if reference.get('run_sha256')!=seal(dict(reference))['run_sha256']:raise ValueError('Historical reference seal mismatch')
        if not fixture:
            om=next(m for m in old_run.schedule('full') if m['seed']==case['seed'] and m['partition']==case['partition'] and m['profile']=='strong' and m['method']=='B')
            old_run.verify_record(reference,om,old_run.plan('full')['strong'],path,False,False)
        item.update(reference_path=str(target.resolve()),reference_sha256=digest(target))
        inputs[cid]=item;refs[cid]=reference;env['inputs']=inputs;write_new(out/'environment.json',env)
        print('Verified input and reference: '+cid,flush=True)
    return refs


def worker(env,out,index):
    check_environment(env);meta=env['schedule'][index];spec=plan(env['preset'])[meta['branch']];entry=env['inputs'][meta['case_id']]
    if digest(Path(entry['path'])/'prepared.json')!=entry['metadata_sha256']:raise ValueError('Input metadata changed')
    if digest(entry['reference_path'])!=entry['reference_sha256']:raise ValueError('Reference changed')
    if meta['branch']=='local_lr':
        baseline_meta=dict(meta,branch='baseline')
        baseline=read(out/'runs'/filename(baseline_meta))
        verify_record(baseline,baseline_meta,plan(env['preset'])['baseline'],entry,env['fixture'])
        baseline_compare(baseline,read(entry['reference_path']))
    p=power_status()
    if not env['fixture'] and p['ac_line_status']!=1:raise RuntimeError('AC power required')
    started=time.time();tick=time.perf_counter()
    with threadpool_limits(limits=1):r=engine_run(entry['path'],spec,branch=meta['branch'],fixture=env['fixture'])
    r.update(worker_started_utc=started,worker_ended_utc=time.time(),engine_wall_seconds=time.perf_counter()-tick,worker_started_power=p,worker_ended_power=power_status())
    r=seal(r);verify_record(r,meta,spec,entry,env['fixture'])
    reference=read(entry['reference_path'])
    if r['initial_head_digest']!=reference['initial_head_digest'] or r['graph_sha256']!=reference['graph_sha256']:raise ValueError('Branches changed initial state or graph')
    if meta['branch']=='baseline':baseline_compare(r,reference)
    write_new(out/'runs'/filename(meta),r)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preset',choices=('full','smoke'),default='full');p.add_argument('--output',type=Path);p.add_argument('--source-results',type=Path,default=ROOT/'experiments/quantity_heterogeneity/results_full');p.add_argument('--diagnostic-results',type=Path,default=ROOT/'experiments/low_capacity_diagnostic/results_full');p.add_argument('--cache',type=Path,default=DIR/'prepared');p.add_argument('--resume',action='store_true');p.add_argument('--worker',type=int,help=argparse.SUPPRESS);a=p.parse_args()
    out=(a.output or DIR/f'results_{a.preset}').resolve()
    if a.worker is not None:worker(read(out/'environment.json'),out,a.worker);return
    if a.resume:
        env=read(out/'environment.json');check_environment(env)
        if (out/'completed.json').exists():
            for name,h in read(out/'completed.json')['files'].items():
                if digest(out/name)!=h:raise ValueError('Completed result changed: '+name)
            if read(out/'finished.json')['completed_manifest_sha256']!=digest(out/'completed.json'):raise ValueError('Finished seal mismatch')
            print('Already complete; manifest verified: '+str(out/'report.md'));return
    else:
        if out.exists() and any(out.iterdir()):raise FileExistsError('Use --resume or a new output')
        env=dict(preset=a.preset,fixture=a.preset=='smoke',plan={b:s.json() for b,s in plan(a.preset).items()},schedule=schedule(a.preset),sources=sources(),runtime=runtime(),source_results=str(a.source_results.resolve()),diagnostic_results=str(a.diagnostic_results.resolve()),public_client_weights={b:public_client_weights(b) for b in plan(a.preset)},cache=str(a.cache.resolve()),plan_commit=PLAN_COMMIT,
                 probe_config=dict(stream=PROBE_STREAM,size=PROBE_SIZES[a.preset],selection='sorted local choice without replacement'),started_utc=time.time())
    pwr=power_status()
    if not env['fixture'] and pwr['ac_line_status']!=1:raise RuntimeError('AC power required before start/resume')
    out.mkdir(parents=True,exist_ok=True);write_new(out/'environment.json',env)
    write_new(out/f'invocation_{time.time_ns()}.json',dict(resume=a.resume,utc=time.time(),power=pwr))
    completed=[]
    with Monitor(out/f'power_{time.time_ns()}.jsonl',interval=15):
        references=prepare_inputs(env,out)
        history=prepare_history(env,out)
        for index,meta in enumerate(env['schedule']):
            path=out/'runs'/filename(meta)
            if not path.exists():
                print('Running: '+path.name,flush=True);subprocess.run([sys.executable,'-m','experiments.local_public_lr.run','--output',str(out),'--worker',str(index)],cwd=ROOT,check=True)
            else:print('Preserved: '+path.name,flush=True)
            r=read(path);verify_record(r,meta,plan(env['preset'])[meta['branch']],env['inputs'][meta['case_id']],env['fixture'])
            if meta['branch']=='baseline':baseline_compare(r,references[meta['case_id']])
            completed.append((meta,r))
        if {p.name for p in (out/'runs').glob('*.json')}!={filename(m) for m in env['schedule']}:raise ValueError('Unexpected result files')
        # Recheck frozen historical inputs after both runs, before sealing.
        prepare_inputs(env,out);prepare_history(env,out)
        reports(out,completed,references,fixture=env['fixture'],history=history);check_environment(env)
    write_new(out/'environment_final.json',dict(**env,ended_utc=time.time(),ended_power=power_status()))
    write_new(out/'completed.json',dict(runs=len(completed),baseline_replays=len(cases(env['preset'])),long_diagnostic_runs=len(completed)-len(cases(env['preset'])),files={str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json','finished.json')}))
    write_new(out/'finished.json',dict(completed_manifest_sha256=digest(out/'completed.json')));print('Finished: '+str(out/'report.md'),flush=True)


if __name__=='__main__':main()
