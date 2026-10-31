"""Paired full-graph B/E/D timing with per-round private-workload caps."""
import argparse
from collections import Counter
import hashlib,json,math,subprocess,sys
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.data import sha,runtime,source_hashes
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.util import load_json,seal_payload,validate_payload,native_peak_bytes
from experiments.noniid_clustering.data import prepare,verify,ensure_data
from .design import PARTITIONS,SEEDS,METHODS,QUALITY_ACC_DROP,plan,spec_from_json
from .sampling import subset_indices,subset_digest
from .student import selected_edges,schedule_digest,Coverage
from .engine import run
from .report import reports

ROOT=Path(__file__).resolve().parents[2]
DESIGN=dict(stage='Private head-workload reduction at a fixed public student budget',
    methods=list(METHODS),partitions=list(PARTITIONS),seeds=list(SEEDS),
    primary_metrics=['head_pipeline_seconds','with_shared_preparation_seconds','paired_absolute_seconds_saved'],
    quality_guardrail_acc_drop=QUALITY_ACC_DROP,
    private_sampling='Per-round subset from SeedSequence [seed,403,client,round]; full cap delegates to the original private_epoch',
    scope='Known-seed paired serial CPU timing; not independent-seed/process timing confirmation',
    memory_scope='Full-private case only, all methods/partitions/seeds; isolated single-method replays; times discarded')
def own_sources():return {p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
def prep_sources():return {p.name:sha(p) for p in sorted((ROOT/'experiments/noniid_clustering').glob('*.py'))}
def check_environment(env):
    if env['source_hashes']!=own_sources() or env['core_source_hashes']!=source_hashes() or env['preparation_source_hashes']!=prep_sources():raise ValueError('Frozen source changed')
    if env['design']!=DESIGN:raise ValueError('Design changed')
    current=runtime()
    if any(current[k]!=env['runtime'][k] for k in ('python','executable','numpy','scipy','sklearn','torch')):raise ValueError('Runtime changed')
    expected=[s.json() for s in plan(env['preset'],env['plan'][0]['config']['prepare_device'])]
    if env['plan']!=expected:raise ValueError('Plan changed')

def save(path,data):
    if path.exists():raise FileExistsError(path)
    tmp=path.with_suffix(path.suffix+'.part');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');tmp.replace(path)

def check_reference(case,reference):
    validate_payload(reference)
    if case['spec']['private_limit'] is not None or reference['case_id']!='m16384_fixed8' or reference['config']!=case['config'] or reference['seed']!=case['seed'] or reference['partition']!=case['partition'] or reference['prepared_directory']!=case['prepared_directory'] or reference['initial_head_digest']!=case['initial_head_digest'] or reference['identity']['core_source_hashes']!=source_hashes():raise ValueError('Anchor reference identity differs')
    old=[r for r in reference['round_records'] if r['method'] in METHODS]
    keys=[(r['round'],r['method']) for r in old];expected={(r,m) for r in range(1,case['config']['rounds']+1) for m in METHODS}
    if len(keys)!=len(expected) or set(keys)!=expected:raise ValueError('Incomplete reference')
    lookup={(r['round'],r['method']):r for r in old}
    for row in case['round_records']:
        before=lookup[(row['round'],row['method'])]
        for k in ('head_digest_after_public','traffic','public_optimizer_steps','student_forward_endpoints','public_loss','persistent_method_array_bytes'):
            if row[k]!=before[k]:raise ValueError('Anchor differs from historical B/E/D: '+k)
    oldmetrics=[q for q in reference['metrics'] if q['method'] in METHODS]
    if oldmetrics!=case['metrics']:raise ValueError('Anchor reference metrics differ')
    return dict(checked=True,round_method_pairs=len(expected),reference_payload_sha256=reference['payload_sha256'])

def check_case(case,spec,part,seed,env,directory,reference=None):
    validate_payload(case);cfg=spec.config;n=len(cfg.dimensions);e=cfg.samples*cfg.degree//2
    if (case['identity']!=env or case['partition']!=part or case['seed']!=seed or case['spec']!=spec.json() or case['config']!=cfg.json()
            or case['case_id']!=spec.case_id or case['dataset']!='Fashion-MNIST' or case['prepared_directory']!=str(directory.resolve())
            or case['partition_audit']!=load_json(directory/'partition.json') or set(case['summary'])!=set(METHODS)):raise ValueError('Case identity differs')
    rr=case['round_records'];keys=[(r['round'],r['method']) for r in rr]
    if len(keys)!=3*cfg.rounds or set(keys)!={(r,m) for r in range(1,cfg.rounds+1) for m in METHODS}:raise ValueError('Incomplete round coverage')
    graph=make_graph(cfg.samples,cfg.degree,seed)
    if case['graph_sha256']!=hashlib.sha256(graph.astype('<u4').tobytes()).hexdigest():raise ValueError('Graph differs')
    observer=Coverage(n,graph,cfg.samples);coverage=[]
    private_counts=case['partition_audit']['diagnostics']['client_counts']
    effective_counts=[k if spec.private_limit is None else min(spec.private_limit,k) for k in private_counts]
    private_steps=sum((k+cfg.private_batch-1)//cfg.private_batch for k in effective_counts)*cfg.private_epochs
    edge_budget=e if spec.policy=='full' else spec.steps*cfg.public_edge_batch
    for rnd in range(1,cfg.rounds+1):
        rows=[r for r in rr if r['round']==rnd]
        for k in ('head_digest_after_public','public_schedule_digest','public_optimizer_steps','student_forward_endpoints','public_edges_consumed','committed_counts_digest','private_loss','public_loss','private_subset_digest','private_samples_per_client','private_subset_pseudo_histograms','private_optimizer_steps','private_forward_endpoints'):
            if any(r[k]!=rows[0][k] for r in rows):raise ValueError('B/E/D differs: '+k)
        if any(r['traffic']!=rows[0]['traffic'] for r in rows):raise ValueError('B/E/D traffic differs')
        orders=[selected_edges(spec,seed,c,rnd) for c in range(n)];expected_schedule=schedule_digest(orders)
        coverage.append(dict(round=rnd,**observer.observe(orders)))
        for r in rows:
            if len(r['received_counts_digests'])!=n or any(h!=r['committed_counts_digest'] for h in r['received_counts_digests']):raise ValueError('Committed/received targets differ')
            if r['public_schedule_digest']!=expected_schedule or r['public_optimizer_steps']!=n*spec.effective_steps or r['public_edges_consumed']!=n*edge_budget or r['private_optimizer_steps']!=private_steps or r['private_forward_endpoints']!=sum(effective_counts)*cfg.private_epochs:raise ValueError('Wrong training schedule or budget')
            idxs=[subset_indices(seed,c,rnd,k,spec.private_limit) for c,k in enumerate(private_counts)]
            if r['private_samples_per_client']!=[len(x) for x in idxs] or r['private_subset_digest']!=subset_digest(idxs):raise ValueError('Private subset differs from frozen sampling schedule')
            if any(len(h)!=cfg.classes or sum(h)!=len(idxs[c]) for c,h in enumerate(r['private_subset_pseudo_histograms'])):raise ValueError('Private subset histogram inconsistent with subset sizes')
            if not 0<=r['teacher_forward_endpoints']<=n*cfg.samples or (r['method']=='B' and r['teacher_forward_endpoints']!=n*cfg.samples):raise ValueError('Wrong teacher scope')
            for phase in ('private','generation','exchange','public','pipeline'):
                if not math.isfinite(r[phase+'_seconds']) or r[phase+'_seconds']<0:raise ValueError('Invalid timing')
    if coverage!=case['coverage_records'] or case['coverage']!=observer.snapshot():raise ValueError('Coverage log differs')
    evalrounds={r for r in range(1,cfg.rounds+1) if r%cfg.eval_every==0 or r==cfg.rounds}
    mk=[(q['round'],q['method']) for q in case['metrics']]
    if len(mk)!=3*len(evalrounds) or set(mk)!={(r,m) for r in evalrounds for m in METHODS}:raise ValueError('Incomplete evaluations')
    for rnd in evalrounds:
        group=[q for q in case['metrics'] if q['round']==rnd]
        if any(q['clients']!=group[0]['clients'] or q['mean']!=group[0]['mean'] for q in group):raise ValueError('B/E/D quality differs')
        for q in group:
            if [c['client'] for c in q['clients']]!=list(range(n)):raise ValueError('Incomplete client metrics')
            for k in ('acc','nmi','ari'):
                if not math.isfinite(q['mean'][k]) or abs(q['mean'][k]-np.mean([c[k] for c in q['clients']]))>1e-12:raise ValueError('Invalid metric mean')
    for m,s in case['summary'].items():
        rows=[r for r in rr if r['method']==m]
        pipeline=s['initialization_seconds']+sum(r['pipeline_seconds'] for r in rows)
        if abs(s['head_pipeline_seconds']-pipeline)>1e-8 or abs(s['with_shared_preparation_seconds']-(case['common_preparation_seconds']+case['shared_loading_seconds']+pipeline))>1e-8:raise ValueError('Summary timing differs')
        for phase in ('private','generation','exchange','public'):
            if abs(s[phase+'_seconds']-sum(r[phase+'_seconds'] for r in rows))>1e-8:raise ValueError('Phase summary differs')
        if abs(s['generation_fraction']-s['generation_seconds']/pipeline)>1e-12 or s['public_optimizer_steps']!=sum(r['public_optimizer_steps'] for r in rows) or s['student_forward_endpoints']!=sum(r['student_forward_endpoints'] for r in rows):raise ValueError('Summary budget/share differs')
        if s['final_head_digest']!=rows[-1]['head_digest_after_public'] or s['final_metrics']!=next(q for q in case['metrics'] if q['method']==m and q['round']==cfg.rounds):raise ValueError('Final summary differs')
        if s['persistent_method_array_bytes']!=rows[-1]['persistent_method_array_bytes']:raise ValueError('Persistent array summary differs')
        traffic=Counter(s['initial_traffic'])
        for row in rows:traffic.update(row['traffic'])
        if dict(traffic)!=s['traffic']:raise ValueError('Traffic ledger differs')
    v=case['validation']
    if not v['enabled'] or v['mismatches']!=0 or v['relation_comparisons']!=3*cfg.rounds*n*e or v['candidate_membership_comparisons']!=2*cfg.rounds*n*cfg.samples:raise ValueError('Wrong oracle coverage')
    ref=dict(checked=False) if reference is None else check_reference(case,reference)
    if case['reference_validation']!=ref:raise ValueError('Reference evidence differs')

def check_profile(profile,case,env):
    validate_payload(profile)
    if profile['identity']!=env or (profile['partition'],profile['seed'],profile['case_id'])!=(case['partition'],case['seed'],case['case_id']) or profile['method'] not in METHODS or profile['process_peak_working_set_bytes']<=0:raise ValueError('Invalid memory profile')
    expected=case['summary'][profile['method']]
    if profile['persistent_method_array_bytes']!=expected['persistent_method_array_bytes'] or profile['final_head_digest']!=expected['final_head_digest']:raise ValueError('Memory replay differs')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset',choices=('full','smoke'),default='full');ap.add_argument('--prepare-device',choices=('cpu','cuda'))
    ap.add_argument('--download',action='store_true');ap.add_argument('--resume',action='store_true');ap.add_argument('--memory-audit',action='store_true')
    ap.add_argument('--cache',type=Path,default=ROOT/'experiments/noniid_clustering/prepared');ap.add_argument('--data-dir',type=Path,default=ROOT/'experiments/real_iid/data');ap.add_argument('--output',type=Path)
    ap.add_argument('--memory-worker',choices=METHODS,help=argparse.SUPPRESS);ap.add_argument('--worker-seed',type=int,help=argparse.SUPPRESS);ap.add_argument('--worker-partition',choices=PARTITIONS,help=argparse.SUPPRESS);ap.add_argument('--worker-case',help=argparse.SUPPRESS)
    args=ap.parse_args();output=(args.output or ROOT/f'experiments/private_workload/results_{args.preset}').resolve()
    if args.memory_worker:
        env=load_json(output/'environment.json');check_environment(env)
        spec=next(s for s in map(spec_from_json,env['plan']) if s.case_id==args.worker_case)
        marker=load_json(output/f'prepared_{args.worker_partition}_seed_{args.worker_seed}.json');directory=Path(marker['path'])
        if sha(directory/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Prepared marker changed')
        verify(directory,spec.config,args.worker_seed,args.worker_partition)
        with threadpool_limits(limits=spec.config.threads):result=run(directory,spec,names=(args.memory_worker,),validate=False,metrics=False,progress=False)
        s=result['summary'][args.memory_worker]
        print(json.dumps(dict(partition=args.worker_partition,seed=args.worker_seed,case_id=spec.case_id,method=args.memory_worker,process_peak_working_set_bytes=native_peak_bytes(),persistent_method_array_bytes=s['persistent_method_array_bytes'],final_head_digest=s['final_head_digest'])))
        return
    if args.resume:
        env=load_json(output/'environment.json');check_environment(env);specs=[spec_from_json(v) for v in env['plan']]
        args.cache=Path(env['cache']);args.data_dir=Path(env['data_dir']);print('Resume uses frozen plan and sources',flush=True)
    else:
        if output.exists() and any(output.iterdir()):raise FileExistsError('Use new output or --resume')
        specs=plan(args.preset,args.prepare_device);references={}
        if args.preset=='full':
            refdir=ROOT/'experiments/public_budget/results_full'
            for seed in SEEDS:
                for part in PARTITIONS:
                    p=refdir/f'{part}_m16384_fixed8_seed_{seed}.json'
                    if p.exists() and load_json(p)['config']==specs[0].config.json():references[f'{part}_{seed}']=dict(path=str(p.resolve()),sha256=sha(p))
        env=dict(preset=args.preset,plan=[s.json() for s in specs],design=DESIGN,source_hashes=own_sources(),core_source_hashes=source_hashes(),preparation_source_hashes=prep_sources(),runtime=runtime(),cache=str(args.cache.resolve()),data_dir=str(args.data_dir.resolve()),memory_audit=args.memory_audit,references=references)
        output.mkdir(parents=True,exist_ok=True);save(output/'environment.json',env)
    ensure_data(args.data_dir,args.download);cases=[];profiles=[]
    with threadpool_limits(limits=specs[0].config.threads):
        for seed in SEEDS:
            for part in PARTITIONS:
                markerpath=output/f'prepared_{part}_seed_{seed}.json'
                if markerpath.exists():
                    marker=load_json(markerpath);directory=Path(marker['path'])
                    if sha(directory/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Prepared identity changed')
                else:
                    directory=prepare(args.cache,args.data_dir,specs[0].config,seed,part,download=args.download)
                    save(markerpath,dict(path=str(directory.resolve()),metadata_sha256=sha(directory/'prepared.json')))
                verify(directory,specs[0].config,seed,part)
                order=list(specs);shift=seed%len(order);order=order[shift:]+order[:shift]
                for spec in order:
                    print(f'{part} {spec.case_id} seed={seed}: full teacher graph, {spec.effective_steps} public steps/client, private limit {spec.private_limit}',flush=True)
                    ref=None;refmeta=env['references'].get(f'{part}_{seed}') if spec.case_id==specs[0].case_id else None
                    if refmeta:
                        if sha(Path(refmeta['path']))!=refmeta['sha256']:raise ValueError('Anchor reference changed')
                        ref=load_json(refmeta['path'])
                    path=output/f'{part}_{spec.case_id}_seed_{seed}.json'
                    if path.exists():
                        case=load_json(path);check_case(case,spec,part,seed,env,directory,ref);print('  preserved completed case',flush=True)
                    else:
                        result=run(directory,spec)
                        case=dict(**result,partition=part,partition_audit=load_json(directory/'partition.json'),identity=env)
                        case['reference_validation']=dict(checked=False) if ref is None else check_reference(case,ref)
                        case=seal_payload(case);check_case(case,spec,part,seed,env,directory,ref);save(path,case)
                    cases.append(case);reports(output,cases,profiles)
                    if env['memory_audit'] and spec.private_limit is None:
                        for m in METHODS:
                            p=output/f'memory_{part}_{spec.case_id}_{m}_seed_{seed}.json'
                            if p.exists():profile=load_json(p)
                            else:
                                cmd=[sys.executable,'-m','experiments.private_workload.run','--output',str(output),'--memory-worker',m,'--worker-seed',str(seed),'--worker-partition',part,'--worker-case',spec.case_id]
                                worker=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
                                if worker.returncode:raise RuntimeError('Isolated memory worker failed: '+worker.stderr)
                                profile=seal_payload(dict(**json.loads(worker.stdout),identity=env));save(p,profile)
                            check_profile(profile,case,env);profiles.append({k:v for k,v in profile.items() if k not in ('identity','payload_sha256')})
                        reports(output,cases,profiles)
    check_environment(env)
    done=dict(case_count=len(cases),training_trajectories=len(cases)*3,memory_replays=len(profiles),mismatches=0,
        relation_comparisons=sum(c['validation']['relation_comparisons'] for c in cases),candidate_membership_comparisons=sum(c['validation']['candidate_membership_comparisons'] for c in cases),
        historical_anchor_round_method_pairs=sum(c['reference_validation'].get('round_method_pairs',0) for c in cases),
        files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='completed.json' and not p.name.endswith('.part')})
    tmp=output/'completed.json.part';tmp.write_text(json.dumps(done,indent=2),encoding='utf-8');tmp.replace(output/'completed.json')
    print(f'Finished: {output/"report.md"}',flush=True)
if __name__=='__main__':main()
