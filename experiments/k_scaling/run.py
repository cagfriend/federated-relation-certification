"""Independent-process K sensitivity study; never changes old experiments."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from threadpoolctl import threadpool_limits
from experiments.public_scaling.data import runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.private_workload.design import spec_from_json
from experiments.stl10_transfer.run import digest,seal,write_new,power_status,check_environment as check_old_environment,check_run as check_old_run
from experiments.stl10_transfer.design import plan as transfer_plan
from experiments.stl10_compute.run import TRAJECTORY_KEYS
from .design import plan,schedule,filename,METHODS
from . import data
from .engine import run as engine_run
from .report import reports

ROOT=Path(__file__).resolve().parents[2];DIR=Path(__file__).parent

def sources():
    # Preserve the full previously frozen dependency closure.
    from experiments.stl10_repeat_confirmation.run import frozen_sources
    out=frozen_sources()
    for p in DIR.glob('*.py'):out[str(p.relative_to(ROOT))]=digest(p)
    out['experiments/k_scaling/PREREGISTRATION.md']=digest(DIR/'PREREGISTRATION.md')
    return out

def environment_check(env):
    if env['sources']!=sources():raise ValueError('Frozen source changed')
    now=runtime()
    for k in ('python','executable','numpy','scipy','sklearn','torch','platform'):
        if now.get(k)!=env['runtime'].get(k):raise ValueError('Runtime changed: '+k)
    if env['plan']!=[s.json() for s in plan(env['preset'])]:raise ValueError('Plan changed')

def non_time_rows(r):
    return [{k:v for k,v in x.items() if not k.endswith('_seconds')} for x in r['round_records']]

def verify_record(r,meta,spec,base,small,memory,fixture):
    # seal() makes an independent shallow dictionary, without changing r.
    if r.get('run_sha256')!=seal(dict(r))['run_sha256']:raise ValueError('Run seal differs')
    for k in ('seed','partition','classes','method'):
        if r.get(k)!=meta[k]:raise ValueError('Run identity differs: '+k)
    if r['spec']!=spec.json() or r['config']!=spec.config.json():raise ValueError('Run config differs')
    if r['prepared_directory']!=str(Path(base).resolve()) or r['pseudo_directory']!=str(Path(small).resolve()):raise ValueError('Input paths differ')
    if r['memory_mode']!=memory or r['dataset']!=('STL-10 fixture' if fixture else 'STL-10'):raise ValueError('Mode or dataset differs')
    cfg=spec.config;n=len(cfg.dimensions);rows=r['round_records']
    if [x['round'] for x in rows]!=list(range(1,cfg.rounds+1)):raise ValueError('Round coverage differs')
    if any(x['method']!=meta['method'] or x['public_optimizer_steps']!=2*n for x in rows):raise ValueError('Method or public steps differ')
    if r['summary'][meta['method']]['final_head_digest']!=rows[-1]['head_digest_after_public']:raise ValueError('Final head differs')
    v=r['validation']
    expected=cfg.rounds*n*cfg.samples*cfg.degree//2
    if memory:
        if v['enabled'] or r['metrics']:raise ValueError('Memory run contains oracle or evaluation')
    elif not v['enabled'] or v['mismatches'] or v['relation_comparisons']!=expected or v['candidate_membership_comparisons']!=(0 if meta['method']=='B' else cfg.rounds*n*cfg.samples):
        raise ValueError('Oracle coverage differs')

def verify_groups(completed):
    groups={}
    for m,r in completed:groups.setdefault((m['partition'],m['seed'],m['classes']),{})[m['method']]=r
    for key,g in groups.items():
        if set(g)!=set(METHODS):raise ValueError('Incomplete triple')
        b=g['B']
        for method in ('E','D'):
            r=g[method]
            if r['initial_head_digest']!=b['initial_head_digest'] or r['graph_sha256']!=b['graph_sha256']:raise ValueError('Initial state differs')
            if [{k:x[k] for k in TRAJECTORY_KEYS} for x in r['round_records']]!=[{k:x[k] for k in TRAJECTORY_KEYS} for x in b['round_records']]:raise ValueError('Trajectory differs: '+str(key))
            if [{k:v for k,v in q.items() if k!='method'} for q in r['metrics']]!=[{k:v for k,v in q.items() if k!='method'} for q in b['metrics']]:raise ValueError('Evaluation differs')
    return groups

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset',choices=('full','smoke'),default='full');ap.add_argument('--output',type=Path)
    ap.add_argument('--source-results',type=Path,default=ROOT/'experiments/stl10_transfer/results_full')
    ap.add_argument('--anchor-results',type=Path,default=ROOT/'experiments/stl10_compute/results_full')
    ap.add_argument('--cache',type=Path,default=DIR/'prepared_k');ap.add_argument('--resume',action='store_true');ap.add_argument('--memory-audit',action='store_true')
    ap.add_argument('--worker',action='store_true');ap.add_argument('--job',type=int);ap.add_argument('--memory-worker',action='store_true')
    a=ap.parse_args();out=(a.output or DIR/f'results_{a.preset}').resolve()
    if a.worker:
        env=json.loads((out/'environment.json').read_text(encoding='utf-8'));environment_check(env)
        m=schedule(env['preset'],a.memory_worker)[a.job];spec=next(s for s in plan(env['preset']) if s.config.classes==m['classes'])
        entry=env['inputs'][f"{m['seed']}|{m['partition']}|{m['classes']}"];base=Path(entry['base']);small=Path(entry['pseudo'])
        if digest(small/'prepared_k.json')!=entry['metadata_sha256']:raise ValueError('Pseudo metadata changed')
        meta=data.verify(small,base,spec,fixture=env['fixture'])
        with threadpool_limits(limits=spec.config.threads):
            r=engine_run(base,spec,data.pseudo_paths(small),method=m['method'],fixture=env['fixture'],validate=not a.memory_worker,metrics=not a.memory_worker)
        r.update(**{k:m[k] for k in ('seed','partition','classes','method')},pseudo_directory=str(small.resolve()),
                 memory_mode=a.memory_worker,additional_kmeans_seconds=meta['additional_kmeans_seconds'],
                 additional_preparation_seconds=meta['additional_preparation_seconds'],process_peak_bytes=native_peak_bytes())
        r=seal(r);verify_record(r,m,spec,base,small,a.memory_worker,env['fixture'])
        write_new(out/('memory' if a.memory_worker else 'runs')/filename(m),r);return
    if a.resume:
        env=json.loads((out/'environment.json').read_text(encoding='utf-8'));environment_check(env)
    else:
        if out.exists() and any(out.iterdir()):raise FileExistsError('Use --resume or a new output')
        fixture=a.preset=='smoke';specs=plan(a.preset);basecfg=transfer_plan(a.preset)[-1].config
        base_inputs={};source=a.source_results.resolve()
        if fixture:
            from experiments.stl10_transfer.data import prepare
            for seed in (1001,):
                for part in ('iid','dirichlet_0.1'):base_inputs[seed,part]=prepare(DIR/'fixture_prepared',DIR/'fixture_data',basecfg,seed,part,fixture=True)
        else:
            check_old_environment(json.loads((source/'environment.json').read_text(encoding='utf-8')))
            for seed in (1001,1002,1003):
                for part in ('iid','dirichlet_0.1'):
                    marker=json.loads((source/f'prepared_{part}_seed_{seed}.json').read_text(encoding='utf-8'));p=Path(marker['path'])
                    if digest(p/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Base cache changed')
                    base_inputs[seed,part]=p
        pwr=power_status()
        if not fixture and pwr['ac_line_status']!=1:raise RuntimeError('AC power required')
        inputs={}
        for (seed,part),base in base_inputs.items():
            for spec in specs:
                print(f'Preparing private pseudo targets: seed={seed}, {part}, K={spec.config.classes}',flush=True)
                p=data.prepare(base,spec,a.cache,fixture=fixture)
                inputs[f'{seed}|{part}|{spec.config.classes}']=dict(base=str(Path(base).resolve()),pseudo=str(p.resolve()),metadata_sha256=digest(p/'prepared_k.json'))
        env=dict(preset=a.preset,fixture=fixture,plan=[s.json() for s in specs],sources=sources(),runtime=runtime(),inputs=inputs,
                 anchor_results=str(a.anchor_results.resolve()),memory_audit=a.memory_audit,started_power=pwr,started_utc=time.time())
        out.mkdir(parents=True,exist_ok=True);write_new(out/'environment.json',env)
    pwr=power_status()
    if not env['fixture'] and pwr['ac_line_status']!=1:raise RuntimeError('AC power required on every invocation')
    write_new(out/f'invocation_{time.time_ns()}.json',dict(resume=a.resume,power=pwr,utc=time.time()))
    anchors={}
    if not env['fixture']:
        from experiments.stl10_compute.design import plan as old_plan
        oldspec=old_plan('full')[0]
        for seed in (1001,1002,1003):
            for part in ('iid','dirichlet_0.1'):
                r=json.loads((Path(env['anchor_results'])/'runs'/f'{part}_{oldspec.case_id}_seed_{seed}_B.json').read_text(encoding='utf-8'))
                check_old_run(r,dict(seed=seed,partition=part,method='B',case_id=oldspec.case_id),oldspec,Path(env['inputs'][f'{seed}|{part}|10']['base']),False)
                anchors[part,seed]=r
    completed=[];memories=[]
    for memory in ((False,True) if env['memory_audit'] else (False,)):
        target_list=memories if memory else completed
        expected=schedule(env['preset'],memory)
        for job,m in enumerate(expected):
            path=out/('memory' if memory else 'runs')/filename(m)
            if not path.exists():
                print(('Memory: ' if memory else 'Running: ')+path.name,flush=True)
                cmd=[sys.executable,'-m','experiments.k_scaling.run','--worker','--job',str(job),'--output',str(out)]
                if memory:cmd.append('--memory-worker')
                subprocess.run(cmd,check=True)
            r=json.loads(path.read_text(encoding='utf-8'));spec=next(s for s in plan(env['preset']) if s.config.classes==m['classes']);entry=env['inputs'][f"{m['seed']}|{m['partition']}|{m['classes']}"]
            verify_record(r,m,spec,entry['base'],entry['pseudo'],memory,env['fixture'])
            if memory:
                reference=next(v for x,v in completed if all(x[k]==m[k] for k in ('seed','partition','classes','method')))
                if non_time_rows(r)!=non_time_rows(reference) or r['initial_head_digest']!=reference['initial_head_digest']:raise ValueError('Memory trajectory differs')
            elif m['classes']==10 and m['method']=='B' and not env['fixture']:
                from experiments.stl10_repeat_confirmation.run import check_anchor_compute
                check_anchor_compute(r,anchors[m['partition'],m['seed']])
            target_list.append((m,r))
        if {p.name for p in (out/('memory' if memory else 'runs')).glob('*.json')}!={filename(m) for m in expected}:raise ValueError('Unexpected result files')
    verify_groups(completed);reports(out,completed,memories,fixture=env['fixture']);environment_check(env)
    write_new(out/'environment_final.json',dict(**env,ended_utc=time.time(),ended_power=power_status(),power_monitoring='start/end and invocation snapshots only'))
    manifest={str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json','finished.json')}
    write_new(out/'completed.json',dict(files=manifest,runs=len(completed),memory_runs=len(memories),mismatches=0))
    write_new(out/'finished.json',dict(status='complete',completed_manifest_sha256=digest(out/'completed.json')))
    print('Finished: '+str(out/'report.md'),flush=True)

if __name__=='__main__':main()
