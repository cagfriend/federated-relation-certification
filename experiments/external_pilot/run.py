"""Small external-method pilot; no formal performance confirmation claims."""
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import torch
from threadpoolctl import threadpool_limits
from .common import Wire,model_digest
from .design import config,schedule
from .prepare import prepare,load,write,read,sha
from .timing import Ledger,observe,difference

ROOT=Path(__file__).resolve().parents[2]

def sources():
    # Freeze all Python dependencies, including existing certified engine.
    return {str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'experiments').rglob('*.py')) if '__pycache__' not in p.parts}

def make(method,models,cfg,wire,train):
    if method=='Ours':
        from .ours import Ours
        return Ours(models,cfg,wire,train['private'],train['public'])
    if method=='Hetero-SSFL':
        from .hetero import Hetero
        return Hetero(models,cfg,wire)
    if method=='FLESD':
        from .flesd import FLESD
        return FLESD(models,cfg,wire)
    from .fedmkd import FedMKD
    return FedMKD(models,cfg,wire)

def worker(out,cfg,case):
    from .evaluate import evaluate
    import psutil
    torch.manual_seed(cfg['seed']);np.random.seed(cfg['seed'])
    models,train,meta=load(out/'cache',case['partition'],cfg)
    initial=model_digest(models)
    evaluation=torch.load(out/'cache'/case['partition']/'evaluation.pt',weights_only=True)
    wire=Wire();ledger=Ledger()
    with observe(ledger,wire):
        start=time.perf_counter()
        with ledger.phase('compute_seconds'):algorithm=make(case['method'],models,cfg,wire,train)
        setup=time.perf_counter()-start
    algorithm.observer=ledger
    if hasattr(algorithm,'protocol'):algorithm.protocol.observer=ledger
    setup_details=dict(timing=ledger.snapshot(),feature_extraction_seconds=getattr(algorithm,'feature_extraction_seconds',0.),
        common_ae_seconds=meta['common_ae_seconds'],data_preparation_seconds=meta.get('data_preparation_seconds'),
        common_preparation_seconds=meta['preparation_seconds'],
        common_ae_dense_macs=5*3072*sum(n*w for n,w in zip(cfg['capacities'],cfg['widths']))*cfg['ae_epochs'],
        common_ae_dense_macs_scope='analytical linear layers forward + backward; no input gradient; excludes activations/loss/optimizer')
    def traffic():return algorithm.traffic() if hasattr(algorithm,'traffic') else wire.snapshot()
    setup_traffic=traffic()
    def observation(rnd,seconds):
        return dict(round=rnd,cumulative_method_seconds=seconds,cumulative_total_seconds=seconds+meta['common_ae_seconds'],
            cumulative_bytes=traffic().get('total_bytes',0),**evaluate(algorithm,train['private'],evaluation,cfg))
    observations=[observation(0,setup)]
    rows=[];audits=0
    for rnd in range(1,cfg['rounds']+1):
        before=ledger.snapshot();previous_traffic=traffic()
        with observe(ledger,wire):
            start=time.perf_counter()
            with ledger.phase('compute_seconds'):stats=algorithm.round(train['private'],train['public'],cfg['seed'],rnd)
            elapsed=time.perf_counter()-start
        if hasattr(algorithm,'audit'):audits+=algorithm.audit()
        if not all(torch.isfinite(t).all() for m in models for t in m.state_dict().values()):raise ValueError('Nonfinite model')
        stages=difference(ledger.snapshot(),before)
        for key in ('compute_seconds','serialization_seconds','aggregation_seconds'):stages.setdefault(key,0.)
        stages['other_seconds']=elapsed-sum(stages.values())
        row=dict(round=rnd,seconds=elapsed,stats=stats,timing=stages,
                 traffic=traffic(),traffic_delta=difference(traffic(),previous_traffic),
                 model_digest=model_digest(models),head_digest=algorithm.state_digest() if hasattr(algorithm,'state_digest') else None)
        rows.append(row)
        if rnd%cfg['eval_every']==0 or rnd==cfg['rounds']:
            observations.append(observation(rnd,setup+sum(r['seconds'] for r in rows)))
            print(f"{case['partition']} {case['method']}: {rnd}/{cfg['rounds']}",flush=True)
    mem=psutil.Process().memory_info()
    result=dict(schema_version=2,case=case,config=cfg,initial_model_digest=initial,cache_files=meta['files'],
        setup_details=setup_details,setup_traffic=setup_traffic,
        source_manifest=read(out/'manifest.json')['sources'],setup_seconds=setup,
        training_seconds=sum(r['seconds'] for r in rows),common_ae_seconds=meta['common_ae_seconds'],
        final_model_digest=model_digest(models),head_digest=algorithm.state_digest() if hasattr(algorithm,'state_digest') else None,
        encoder_frozen=model_digest(models)==initial,rows=rows,evaluations=observations,
        relation_comparisons=audits,mismatches=0 if case['method']=='Ours' else None,
        peak_process_bytes=getattr(mem,'peak_wset',None),rss_at_end_bytes=mem.rss,
        memory_scope='process including observers, not isolated algorithm memory',
        traffic=rows[-1]['traffic'])
    reference=read(out/'manifest.json').get('reference')
    if reference:
        path=Path(reference)/'runs'/f"{case['partition']}_{case['method']}.json"
        old=read(path)
        if len(old['rows'])!=cfg['rounds'] or [r['round'] for r in old['rows']]!=list(range(1,cfg['rounds']+1)):
            raise ValueError('Incomplete reference rounds')
        if [e['round'] for e in old['evaluations']]!=[e['round'] for e in observations]:raise ValueError('Incomplete reference evaluations')
        for key in ('config','initial_model_digest','final_model_digest','head_digest','traffic'):
            if old[key]!=result[key]:raise ValueError('Observation-only reference mismatch: '+key)
        for a,b in zip(old['rows'],rows):
            for key,value in a['stats'].items():
                if not key.endswith('_seconds') and b['stats'][key]!=value:raise ValueError('Changed training statistics')
        for a,b in zip(old['evaluations'],observations):
            if [c['client'] for c in a['clients']]!=list(range(len(models))):raise ValueError('Incomplete reference clients')
            if any(b['mean'][key]!=value for key,value in a['mean'].items()):raise ValueError('Changed evaluation trajectory')
            for old_client,new_client in zip(a['clients'],b['clients']):
                for key,value in old_client.items():
                    if key=='native_head':
                        if any(new_client[key][k]!=v for k,v in value.items()):raise ValueError('Changed native quality')
                    elif new_client[key]!=value:raise ValueError('Changed client quality')
        result['reference_validation']=dict(path=str(path),sha256=sha(path),passed=True,rounds=cfg['rounds'])
    write(out/'runs'/f"{case['partition']}_{case['method']}.json",result)

def profile_worker(out,cfg,case):
    """Count in a fresh process, never use replay wall time for performance."""
    from .cost import CostCounter
    from .evaluate import evaluate
    torch.manual_seed(cfg['seed']);np.random.seed(cfg['seed'])
    models,train,meta=load(out/'cache',case['partition'],cfg)
    measured=read(out/'runs'/f"{case['partition']}_{case['method']}.json")
    counter=CostCounter()
    with counter:
        algorithm=make(case['method'],models,cfg,Wire(),train)
    setup_compute=counter.snapshot()
    counter.prepare(algorithm)
    evaluate(algorithm,train['private'],torch.load(out/'cache'/case['partition']/'evaluation.pt',weights_only=True),cfg)
    costs=[]
    for rnd in range(1,cfg['rounds']+1):
        before=counter.snapshot()
        with counter:algorithm.round(train['private'],train['public'],cfg['seed'],rnd)
        after=counter.snapshot();costs.append(difference(after,before))
        expected=measured['rows'][rnd-1]
        if model_digest(models)!=expected['model_digest']:raise ValueError('Compute replay changed model trajectory')
        if hasattr(algorithm,'state_digest') and algorithm.state_digest()!=expected['head_digest']:raise ValueError('Compute replay changed head trajectory')
        if rnd%cfg['eval_every']==0 or rnd==cfg['rounds']:
            q=evaluate(algorithm,train['private'],torch.load(out/'cache'/case['partition']/'evaluation.pt',weights_only=True),cfg)
            expected_q=next(e for e in measured['evaluations'] if e['round']==rnd)
            if q['clients']!=expected_q['clients']:raise ValueError('Compute replay changed quality')
    write(out/'profiles'/f"{case['partition']}_{case['method']}.json",dict(setup=setup_compute,rounds=costs,
        trajectory_verified=True,measured_sha256=sha(out/'runs'/f"{case['partition']}_{case['method']}.json"),coverage=counter.coverage))

def report(out,cfg):
    lines=['# External-method exploratory pilot','',
        'Small architecture/budget adaptations, not official reproductions. One seed; no significance claim.',
        'Times include all client and coordinator training, serialization and method setup. Evaluation excluded.',
        'Ours freezes features; external methods update encoders. Differences are whole-method costs, not certification-only gains.',
        'Common AE preparation is listed separately and charged once per method. Communication is implementation-specific serialized bytes, not a common-codec lower bound. Public images pre-provisioned.',
        '', '| Partition | Method | Setup + training (s) | With common AE (s) | Bytes | ACC | NMI | Largest cluster |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for case in schedule(cfg):
        r=read(out/'runs'/f"{case['partition']}_{case['method']}.json")
        q=r['evaluations'][-1]['mean'];t=r['setup_seconds']+r['training_seconds']
        lines.append(f"| {case['partition']} | {case['method']} | {t:.3f} | {t+r['common_ae_seconds']:.3f} | {r['traffic']['total_bytes']} | {q['acc']:.4f} | {q['nmi']:.4f} | {q['largest']:.4f} |")
    lines.extend(['','Quality: same unsupervised private-fit KMeans / held-out test protocol; Ours uses head probabilities and externals encoder features. Native Ours head metrics also recorded per client. Do not use KMeans scores to hide native head collapse.','Memory is process peak including evaluation, not an isolated training measurement. No network latency, election, or failure claims.'])
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('--preset',choices=['pilot','smoke'],default='pilot')
    p.add_argument('--output');p.add_argument('--resume',action='store_true')
    p.add_argument('--data-dir',default=str(ROOT/'experiments/stl10_transfer/data/stl10_binary'))
    p.add_argument('--reference',help='Previous results for unchanged-trajectory verification')
    p.add_argument('--profile-worker',type=int,help=argparse.SUPPRESS)
    p.add_argument('--worker',type=int,help=argparse.SUPPRESS);a=p.parse_args();cfg=config(a.preset)
    torch.set_num_threads(1);torch.set_num_interop_threads(1)
    out=Path(a.output or ROOT/f'experiments/external_pilot/results_{a.preset}_observed').resolve()
    with threadpool_limits(limits=1):
        if a.worker is not None:
            if read(out/'manifest.json')['sources']!=sources():raise ValueError('Source changed during run')
            worker(out,cfg,schedule(cfg)[a.worker]);return
        if a.profile_worker is not None:
            if read(out/'manifest.json')['sources']!=sources():raise ValueError('Source changed during replay')
            profile_worker(out,cfg,schedule(cfg)[a.profile_worker]);return
        reference=Path(a.reference).resolve() if a.reference else (ROOT/'experiments/external_pilot/results_pilot' if a.preset=='pilot' else None)
        manifest=dict(config=cfg,sources=sources(),reference=str(reference) if reference else None,schema_version=2)
        if (out/'manifest.json').exists():
            if not a.resume:raise ValueError('Output exists; use --resume or a new --output')
            if read(out/'manifest.json')!=manifest:raise ValueError('Frozen source/config changed; choose a new output')
        else:
            if out.exists() and any(out.iterdir()):raise ValueError('Nonempty output without manifest')
            write(out/'manifest.json',manifest)
        prepare(out/'cache',a.data_dir,cfg)
        if reference:
            for partition in cfg['partitions']:
                old_meta=read(reference/'cache'/partition/'manifest.json')
                new_meta=read(out/'cache'/partition/'manifest.json')
                if old_meta['config']!=cfg or old_meta['initial_model_digest']!=new_meta['initial_model_digest'] or old_meta['files']!=new_meta['files']:
                    raise ValueError('Preparation no longer matches the original experiment')
        for idx,case in enumerate(schedule(cfg)):
            dest=out/'runs'/f"{case['partition']}_{case['method']}.json"
            if dest.exists():
                r=read(dest);meta=read(out/'cache'/case['partition']/'manifest.json')
                if r['config']!=cfg or r['case']!=case or r['source_manifest']!=manifest['sources'] or r['cache_files']!=meta['files'] or r['initial_model_digest']!=meta['initial_model_digest'] or len(r['rows'])!=cfg['rounds']:raise ValueError('Invalid resume result')
                if r.get('schema_version')!=2:raise ValueError('Missing observers')
                print('Retaining '+dest.name,flush=True)
            else:
                print('Running '+dest.name,flush=True)
                env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',LOKY_MAX_CPU_COUNT='1')
                subprocess.run([sys.executable,'-m','experiments.external_pilot.run','--preset',a.preset,'--output',str(out),'--worker',str(idx)],cwd=ROOT,env=env,check=True)
        # Keep profiling work after all timing runs, so it cannot warm up a paired timing run.
        for idx,case in enumerate(schedule(cfg)):
            dest=out/'runs'/f"{case['partition']}_{case['method']}.json"
            profile=out/'profiles'/dest.name
            if profile.exists():
                info=read(profile)
                if info['measured_sha256']!=sha(dest) or not info['trajectory_verified']:raise ValueError('Stale compute profile')
                continue
            print('Counting operations '+dest.name,flush=True)
            env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',LOKY_MAX_CPU_COUNT='1')
            subprocess.run([sys.executable,'-m','experiments.external_pilot.run','--preset',a.preset,'--output',str(out),'--profile-worker',str(idx)],cwd=ROOT,env=env,check=True)
        report(out,cfg)
        from .observations_report import export
        export(out,cfg)
        write(out/'completed.json',dict(runs=len(schedule(cfg)),files={p.name:sha(p) for p in (out/'runs').glob('*.json')},
            profiles={p.name:sha(p) for p in (out/'profiles').glob('*.json')}))
        print('Finished: '+str(out/'report.md'),flush=True)

if __name__=='__main__':main()
