"""All-client correction and full-duration guard strength exploration."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import hashlib
import numpy as np
import torch
from threadpoolctl import threadpool_limits
from experiments.external_pilot.design import config
from experiments.external_pilot.prepare import load,read,write,sha
from experiments.external_pilot.common import Wire,model_digest
from .engine import CorrectedGuardOurs
from experiments.external_pilot.evaluate import evaluate
from experiments.external_pilot.run import sources,ROOT
from experiments.head_initialization.probes import distribution

def cases(cfg):
    settings=[dict(setting='legacy_centers',strength=0.,until=0,all_clients=False)]
    settings += [dict(setting=f'corrected_guard_{v:g}',strength=v,until=cfg['rounds'],all_clients=True)
                 for v in (0.,.1,.5,1.,2.)]
    return [dict(partition=p,initialization='centers',**setting) for p in cfg['partitions'] for setting in settings]

def name(case):return case['partition']+'_'+case['setting']+'.json'

def seal_result(path):
    write(path.with_suffix('.sha256.json'),dict(sha256=sha(path)))

def verify_seal(path):
    receipt=path.with_suffix('.sha256.json')
    if not receipt.exists() or read(receipt).get('sha256')!=sha(path):
        raise ValueError('Run checksum missing or changed: '+str(path))

def digest(a):return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()

def check_reference(new,old):
    assert new['config']==old['config'] and new['initial_model_digest']==old['initial_model_digest']
    assert len(new['rows'])==len(old['rows'])
    for a,b in zip(new['rows'],old['rows']):
        assert a['round']==b['round']
        for key in ('model_digest','head_digest','traffic'):assert a[key]==b[key],key
        for key,val in b['stats'].items():
            if not key.endswith('_seconds'):assert a['stats'][key]==val,key
    assert len(new['evaluations'])==len(old['evaluations'])
    for a,b in zip(new['evaluations'],old['evaluations']):
        assert a['round']==b['round'] and a['mean']==b['mean']
        for x,y in zip(a['clients'],b['clients']):
            assert all(x[k]==v for k,v in y.items())

def worker(out,cfg,case,reference,baseline):
    torch.manual_seed(cfg['seed']);np.random.seed(cfg['seed'])
    models,train,meta=load(reference/'cache',case['partition'],cfg)
    evaluation=torch.load(reference/'cache'/case['partition']/'evaluation.pt',weights_only=True)
    observations=[];probe_seconds=0.;a=None
    def probe(algorithm,rnd,stage):
        nonlocal probe_seconds
        start=time.perf_counter();clients=[]
        for c,h in enumerate(algorithm.heads):
            clients.append(dict(client=c,private=distribution(algorithm.private[c],h.w,h.b,cfg['classes'],algorithm.pseudo[c]),
                public=distribution(algorithm.public[c],h.w,h.b,cfg['classes'])))
        for c,h in enumerate(algorithm.heads):
            pred=(algorithm.private[c]@h.w.T+h.b).argmax(1);y=algorithm.pseudo[c]
            clients[c]['private']['pseudo_recall']=[float(np.mean(pred[y==k]==k)) if np.any(y==k) else None for k in range(cfg['classes'])]
        teacher=None;target=None
        if stage=='T1':
            teacher=[float(np.mean((z@h.w.T+h.b).argmax(1)[algorithm.edges[:,0]]==(z@h.w.T+h.b).argmax(1)[algorithm.edges[:,1]])) for z,h in zip(algorithm.public,algorithm.heads)]
        if stage=='T2':
            teacher=[float(np.mean(r)) for r in algorithm.last_relations]
            if teacher!=observations[-1]['teacher_positive_rates']:raise ValueError('T1 probe differs from actual teacher relations')
            counts=algorithm.protocol.counts
            target=dict(mean=float(counts.mean()/6),minimum=float(counts.min()/6),maximum=float(counts.max()/6),
                count_histogram=np.bincount(counts,minlength=7).tolist(),digest=digest(counts))
        observations.append(dict(round=rnd,stage=stage,clients=clients,teacher_positive_rates=teacher,committed_target=target))
        probe_seconds+=time.perf_counter()-start
    start=time.perf_counter()
    a=CorrectedGuardOurs(models,cfg,Wire(),train['private'],train['public'],initialization='centers',diagnostic_callback=probe,strength=case['strength'],until=case['until'],all_clients=case['all_clients'])
    setup=time.perf_counter()-start
    init_checks=[]
    for c,(z,h,centers,pseudo) in enumerate(zip(a.private,a.heads,a.centers,a.pseudo)):
        distance=((z[:,None,:]-centers[None,:,:])**2).sum(2)
        nearest=distance.argmin(1);pred=(z@h.w.T+h.b).argmax(1)
        ordered=np.sort(distance,axis=1);gap=ordered[:,1]-ordered[:,0]
        near=gap<=128*np.finfo(float).eps*z.shape[1]*(1+abs(distance).max(1))
        if case['initialization']=='centers' and np.any((pred!=nearest)&~near):raise ValueError('Center conversion changed non-tied nearest center')
        init_checks.append(dict(client=c,head_weight_norm=float(np.linalg.norm(h.w)),head_bias_norm=float(np.linalg.norm(h.b)),
            pseudo_histogram=np.bincount(pseudo,minlength=cfg['classes']).tolist(),pseudo_digest=digest(pseudo),centers_digest=digest(centers),
            pseudo_match=float(np.mean(pred==pseudo)),nearest_match=float(np.mean(pred==nearest)),near_ties=int(near.sum()),
            nearest_mismatches=int(np.sum(pred!=nearest)),non_tied_mismatches=int(np.sum((pred!=nearest)&~near))))
    probe(a,0,'initial')
    # Fixed test features are read-only diagnostics, not an additional training cache.
    diagnostic_start=time.perf_counter()
    with torch.no_grad():test_features=[m.encode(evaluation['test']).double().numpy() for m in models]
    def test(rnd):
        q=evaluate(a,train['private'],evaluation,cfg)
        for c,h in enumerate(a.heads):q['clients'][c]['native_confidence']=distribution(test_features[c],h.w,h.b,cfg['classes'])
        return dict(round=rnd,**q)
    tests=[test(0)];evaluation_seconds=time.perf_counter()-diagnostic_start
    rows=[];comparisons=0;oracle_seconds=0.
    for rnd in range(1,cfg['rounds']+1):
        pbefore=probe_seconds;start=time.perf_counter();stats=a.round(train['private'],train['public'],cfg['seed'],rnd)
        elapsed=time.perf_counter()-start;excluded=probe_seconds-pbefore
        start=time.perf_counter();comparisons+=a.audit();oracle_seconds+=time.perf_counter()-start
        rows.append(dict(round=rnd,seconds=elapsed-excluded,probe_seconds=excluded,stats=stats,
            head_digest=a.state_digest(),model_digest=model_digest(models),traffic=a.traffic()))
        if rnd%cfg['eval_every']==0 or rnd==cfg['rounds']:
            start=time.perf_counter();tests.append(test(rnd));evaluation_seconds+=time.perf_counter()-start
            print(f"{case['partition']} {case['setting']}: {rnd}/{cfg['rounds']}",flush=True)
    result=dict(case=case,config=cfg,input_manifest_sha256=sha(out/'manifest.json'),initial_model_digest=meta['initial_model_digest'],cache_files=meta['files'],
        private_correction=dict(all_clients=case['all_clients'],log_priors=[x.tolist() for x in a.all_log_priors]),setup=dict(seconds=setup,feature_extraction_seconds=a.feature_extraction_seconds,conversion_seconds=a.initialization_seconds,
            historical_common_ae_seconds=meta['common_ae_seconds'],cache_reused=True),initial_checks=init_checks,
        rows=rows,diagnostics=observations,evaluations=tests,probe_seconds=probe_seconds,evaluation_seconds=evaluation_seconds,
        oracle_seconds=oracle_seconds,relation_comparisons=comparisons,mismatches=0,traffic=a.traffic())
    if case['setting']=='legacy_centers':
        path=baseline/'runs'/f"{case['partition']}_centers.json";check_reference(result,read(path))
        result['reference_validation']=dict(passed=True,sha256=sha(path),path=str(path))
    path=out/'runs'/name(case)
    write(path,result)
    seal_result(path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--preset',choices=['pilot','smoke'],default='pilot')
    p.add_argument('--baseline');p.add_argument('--reference');p.add_argument('--output');p.add_argument('--resume',action='store_true');p.add_argument('--worker',type=int,help=argparse.SUPPRESS)
    args=p.parse_args()
    cfg=config(args.preset);torch.set_num_threads(1);torch.set_num_interop_threads(1)
    reference=Path(args.reference or ROOT/('experiments/external_pilot/results_pilot_observed' if args.preset=='pilot' else 'outputs/private_corrected_guard_checks/reference')).resolve()
    baseline=Path(args.baseline or ROOT/('experiments/head_initialization/results_pilot' if args.preset=='pilot' else 'outputs/private_corrected_guard_checks/baseline')).resolve()
    out=Path(args.output or ROOT/f'experiments/private_corrected_guard/results_{args.preset}').resolve()
    for part in cfg['partitions']:
        load(reference/'cache',part,cfg)
    refs={str(f.relative_to(reference)):sha(f) for part in cfg['partitions'] for f in [reference/'cache'/part/'manifest.json']}
    manifest=dict(config=cfg,reference=str(reference),reference_hashes=refs,sources=sources(),design_sha256=sha(Path(__file__).with_name('README.md')),baseline=str(baseline),baseline_hashes={part:sha(baseline/'runs'/f'{part}_centers.json') for part in cfg['partitions']},schedule=cases(cfg))
    with threadpool_limits(1):
        if args.worker is not None:
            if manifest!=read(out/'manifest.json'):raise ValueError('Input/source/plan changed')
            worker(out,cfg,cases(cfg)[args.worker],reference,baseline);return
        if (out/'manifest.json').exists():
            if not args.resume or read(out/'manifest.json')!=manifest:raise ValueError('Existing output changed; use --resume with identical inputs or a new output')
        else:
            if out.exists() and any(out.iterdir()):raise ValueError('Output not empty')
            write(out/'manifest.json',manifest)
        for i,case in enumerate(cases(cfg)):
            path=out/'runs'/name(case)
            if path.exists():
                verify_seal(path)
                r=read(path)
                if r['case']!=case or r['config']!=cfg or len(r['rows'])!=cfg['rounds'] or r['mismatches']!=0:raise ValueError('Incomplete result')
                if r['input_manifest_sha256']!=sha(out/'manifest.json'):raise ValueError('Result provenance changed')
                if len(r['diagnostics'])!=3*cfg['rounds']+1 or r['relation_comparisons']!=6*(cfg['public_size']//2)*cfg['rounds']:raise ValueError('Incomplete audits/diagnostics')
                if [row['round'] for row in r['rows']]!=list(range(1,cfg['rounds']+1)):raise ValueError('Missing rounds')
                if (out/'completed.json').exists() and read(out/'completed.json')['hashes'][path.name]!=sha(path):raise ValueError('Completed result changed')
                print('Retaining '+path.name,flush=True);continue
            print(f"Starting {i+1}/{len(cases(cfg))}: {path.name}",flush=True)
            env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',LOKY_MAX_CPU_COUNT='1')
            subprocess.run([sys.executable,'-m','experiments.private_corrected_guard.run','--preset',args.preset,'--reference',str(reference),'--output',str(out),'--baseline',str(baseline),'--worker',str(i)],cwd=ROOT,env=env,check=True)
        from .report import build
        initialization_checks=0
        for partition in cfg['partitions']:
            rr=[read(out/'runs'/name(c)) for c in cases(cfg) if c['partition']==partition]
            for r in rr[1:]:
                for x,y in zip(rr[0]['initial_checks'],r['initial_checks']):
                    if x['centers_digest']!=y['centers_digest'] or x['pseudo_digest']!=y['pseudo_digest']:
                        raise ValueError('Different initialization inputs')
            initialization_checks+=6*(len(rr)-1)
        build(out)
        write(out/'completed.json',dict(runs=len(cases(cfg)),initialization_checks=initialization_checks,hashes={p.name:sha(p) for p in (out/'runs').glob('*.json') if not p.name.endswith('.sha256.json')}))
        print('Finished: '+str(out/'report.md'),flush=True)

if __name__=='__main__':main()
