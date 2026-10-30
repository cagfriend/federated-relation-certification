"""Private-only preparation per split; paired real Local/B/E/D SGD."""
import argparse
from dataclasses import replace
import json
import math
from pathlib import Path
import subprocess
import sys

from threadpoolctl import threadpool_limits
from experiments.public_scaling.config import preset,from_json
from experiments.public_scaling.data import sha,runtime,source_hashes
from experiments.public_scaling.util import load_json,seal_payload,validate_payload,native_peak_bytes
from .data import PARTITIONS,prepare,verify
from .engine import NAMES,run
from .report import reports

ROOT=Path(__file__).resolve().parents[2]


def own_sources():return {p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}


def check_case(case,config,seed,partition,identity,directory):
    validate_payload(case)
    if (case['identity']!=identity or case['config']!=config.json() or case['seed']!=seed
            or case['partition']!=partition or case['dataset']!='Fashion-MNIST'
            or case['prepared_directory']!=str(directory.resolve())
            or set(case['summary'])!=set(NAMES) or not case['validation']['enabled'] or case['validation']['mismatches']!=0):
        raise ValueError('Checkpoint identity mismatch')
    if case['partition_audit']!=load_json(directory/'partition.json'):
        raise ValueError('Saved partition audit differs from prepared manifest')
    rr=case['round_records'];n=len(config.dimensions);edges=config.samples*config.degree//2
    keys=[(r['round'],r['method']) for r in rr]
    expected={(r,m) for r in range(1,config.rounds+1) for m in NAMES}
    if len(keys)!=len(expected) or set(keys)!=expected:raise ValueError('Incomplete round coverage')
    if (case['validation']['relation_comparisons']!=3*config.rounds*n*edges
            or case['validation']['candidate_membership_comparisons']!=2*config.rounds*n*config.samples):
        raise ValueError('Incorrect oracle coverage')
    for rnd in range(1,config.rounds+1):
        group=[r for r in rr if r['round']==rnd and r['method']!='Local']
        if len({r['head_digest_after_public'] for r in group})!=1 or any(r['traffic']!=group[0]['traffic'] for r in group):
            raise ValueError('B/E/D saved trajectory/traffic differs')
    for row in rr:
        for key in ('private_seconds','generation_seconds','exchange_seconds','public_seconds','pipeline_seconds'):
            if not math.isfinite(row[key]) or row[key]<0:raise ValueError('Invalid timing')
        if row['method']=='Local' and (row['traffic'] or row['public_optimizer_steps'] or row['teacher_forward_endpoints'] or row['student_forward_endpoints']):
            raise ValueError('Local accidentally collaborates')
    rounds=[r for r in range(1,config.rounds+1) if r%config.eval_every==0 or r==config.rounds]
    mk=[(q['round'],q['method']) for q in case['metrics']]
    if len(mk)!=len(rounds)*4 or set(mk)!={(r,m) for r in rounds for m in NAMES}:raise ValueError('Incomplete metrics')
    for rnd in rounds:
        group=[q for q in case['metrics'] if q['round']==rnd and q['method']!='Local']
        if any(q['clients']!=group[0]['clients'] for q in group):raise ValueError('B/E/D metrics differ')
    for name,s in case['summary'].items():
        rows=[r for r in rr if r['method']==name]
        expected_cost=s['initialization_seconds']+sum(r['pipeline_seconds'] for r in rows)
        if abs(s['head_pipeline_seconds']-expected_cost)>1e-8:raise ValueError('Summary timing mismatch')
        if s['final_head_digest']!=rows[-1]['head_digest_after_public']:raise ValueError('Final head differs')
        if s['final_metrics']!=next(q for q in case['metrics'] if q['method']==name and q['round']==config.rounds):
            raise ValueError('Final metric mismatch')


def save(path,value):
    if path.exists():raise FileExistsError(path)
    temporary=path.with_suffix(path.suffix+'.part')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    temporary.replace(path)


def check_environment(env):
    if env['source_hashes']!=own_sources() or env['core_source_hashes']!=source_hashes():
        raise ValueError('Source changed; use a fresh output/cache')
    current=runtime()
    if any(env['runtime'][k]!=current[k] for k in ('python','executable','numpy','scipy','sklearn','torch')):
        raise ValueError('Runtime changed')


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset',choices=('full','smoke'),default='full')
    ap.add_argument('--prepare-device',choices=('cpu','cuda'));ap.add_argument('--download',action='store_true')
    ap.add_argument('--data-dir',type=Path,default=ROOT/'experiments/real_iid/data')
    ap.add_argument('--cache',type=Path,default=ROOT/'experiments/noniid_clustering/prepared')
    ap.add_argument('--output',type=Path);ap.add_argument('--resume',action='store_true')
    ap.add_argument('--memory-audit',action='store_true',help='36 additional isolated single-method replays, times discarded')
    ap.add_argument('--memory-worker',choices=NAMES,help=argparse.SUPPRESS)
    ap.add_argument('--worker-seed',type=int,help=argparse.SUPPRESS)
    ap.add_argument('--partition',choices=PARTITIONS,help=argparse.SUPPRESS)
    args=ap.parse_args();output=(args.output or ROOT/f'experiments/noniid_clustering/results_{args.preset}').resolve()
    if args.memory_worker:
        env=load_json(output/'environment.json');check_environment(env);config=from_json(env['config'])
        marker=load_json(output/f'prepared_{args.partition}_seed_{args.worker_seed}.json');directory=Path(marker['path'])
        if sha(directory/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Prepared marker changed')
        verify(directory,config,args.worker_seed,args.partition)
        with threadpool_limits(limits=config.threads):
            result=run(directory,config,names=(args.memory_worker,),validate=False,metrics=False,progress=False)
        s=result['summary'][args.memory_worker]
        print(json.dumps(dict(partition=args.partition,seed=args.worker_seed,method=args.memory_worker,
            persistent_array_bytes=s['persistent_method_array_bytes'],process_peak_working_set_bytes=native_peak_bytes(),
            final_head_digest=s['final_head_digest'])))
        return
    if args.resume:
        env=load_json(output/'environment.json');check_environment(env);config=from_json(env['config'])
        args.cache=Path(env['cache']);args.data_dir=Path(env['data_dir'])
        print('Resume uses frozen preset/device/memory options and plan',flush=True)
    else:
        if output.exists() and any(output.iterdir()):raise FileExistsError('Use fresh output or --resume')
        config=preset(args.preset)
        if args.prepare_device:config=replace(config,prepare_device=args.prepare_device)
        config.validate()
        env=dict(config=config.json(),preset=args.preset,partitions=list(PARTITIONS),seeds=[404,505,606],
            source_hashes=own_sources(),core_source_hashes=source_hashes(),runtime=runtime(),
            cache=str(args.cache.resolve()),data_dir=str(args.data_dir.resolve()),memory_audit=args.memory_audit)
        output.mkdir(parents=True,exist_ok=True);save(output/'environment.json',env)
    cases=[];profiles=[];public_ids_by_seed={}
    with threadpool_limits(limits=config.threads):
        for seed in env['seeds']:
            order=list(PARTITIONS);shift=seed%len(order);order=order[shift:]+order[:shift]
            for partition in order:
                print(f'{partition} seed={seed}: private-only preparation',flush=True)
                marker_path=output/f'prepared_{partition}_seed_{seed}.json'
                if marker_path.exists():
                    marker=load_json(marker_path);directory=Path(marker['path'])
                    if sha(directory/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Prepared metadata changed')
                else:
                    directory=prepare(args.cache,args.data_dir,config,seed,partition,download=args.download)
                    save(marker_path,dict(path=str(directory.resolve()),metadata_sha256=sha(directory/'prepared.json')))
                verify(directory,config,seed,partition)
                public_hash=sha(directory/'public_ids.npy')
                if seed in public_ids_by_seed and public_ids_by_seed[seed]!=public_hash:
                    raise AssertionError('Partitions do not share the same public pool')
                public_ids_by_seed[seed]=public_hash
                path=output/f'{partition}_seed_{seed}.json'
                if path.exists():
                    case=load_json(path);check_case(case,config,seed,partition,env,directory)
                    print('  preserved completed case',flush=True)
                else:
                    result=run(directory,config)
                    case=seal_payload(dict(**result,partition=partition,identity=env,
                        partition_audit=load_json(directory/'partition.json')))
                    check_case(case,config,seed,partition,env,directory);save(path,case)
                cases.append(case);reports(output,cases,profiles)
                if env['memory_audit']:
                    for name in NAMES:
                        profile_path=output/f'memory_{partition}_seed_{seed}_{name}.json'
                        if profile_path.exists():
                            profile=load_json(profile_path);validate_payload(profile)
                            if profile['identity']!=env:raise ValueError('Memory identity changed')
                        else:
                            cmd=[sys.executable,'-m','experiments.noniid_clustering.run','--output',str(output),
                                 '--memory-worker',name,'--partition',partition,'--worker-seed',str(seed)]
                            completed=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,check=True)
                            profile=seal_payload(dict(**json.loads(completed.stdout),identity=env))
                            save(profile_path,profile)
                        expected=case['summary'][name]
                        if (profile['partition']!=partition or profile['seed']!=seed or profile['method']!=name
                                or profile['persistent_array_bytes']!=expected['persistent_method_array_bytes']
                                or profile['final_head_digest']!=expected['final_head_digest']
                                or not profile['process_peak_working_set_bytes'] or profile['process_peak_working_set_bytes']<=0):
                            raise ValueError('Memory replay does not match paired training')
                        profiles.append({k:v for k,v in profile.items() if k not in ('identity','payload_sha256')})
                    reports(output,cases,profiles)
    done=dict(case_count=len(cases),training_trajectories=len(cases)*4,memory_replays=len(profiles),mismatches=0,
        relation_comparisons=sum(c['validation']['relation_comparisons'] for c in cases),
        candidate_membership_comparisons=sum(c['validation']['candidate_membership_comparisons'] for c in cases),
        files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='completed.json' and not p.name.endswith('.part')})
    temporary=output/'completed.json.part'
    temporary.write_text(json.dumps(done,indent=2),encoding='utf-8')
    temporary.replace(output/'completed.json')
    print(f'Finished: {output / "report.md"}',flush=True)


if __name__=='__main__':main()
