"""Run matched-budget target ablations with frozen preparation and identities."""
import argparse
from dataclasses import replace
import hashlib,json,math
from pathlib import Path
from collections import Counter
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.config import preset,from_json
from experiments.public_scaling.data import sha,runtime,source_hashes,idx
from experiments.public_scaling.util import load_json,seal_payload,validate_payload
from experiments.noniid_clustering.data import PARTITIONS,prepare,verify,ensure_data
from .targets import NAMES,TARGETS,validate_record
from .engine import run
from .report import reports

ROOT=Path(__file__).resolve().parents[2]
SEEDS=(404,505,606)
DESIGN=dict(primary_partition='dirichlet_0.1',primary_metric='final_mean_acc',
    minimum_practical_acc_difference=0.005,
    screening='Aggregate-Self and Aggregate-Shuffled each all 3 seeds positive and median >=0.005; exploratory only',
    shuffle='Shared permutation of each branch own aggregate vector after receiving committed counts, seed/906/round',
    probe='round1, every eval_every and final; same post-private snapshot and independent fixed probe batches',
    timing='Diagnostic only; not independent D/E performance confirmation')

def own_sources():return {p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
def preparation_sources():return {p.name:sha(p) for p in sorted((ROOT/'experiments/noniid_clustering').glob('*.py'))}
def environment_check(env):
    if env['source_hashes']!=own_sources() or env['core_source_hashes']!=source_hashes() or env['preparation_source_hashes']!=preparation_sources():raise ValueError('Frozen source changed; use fresh output')
    now=runtime()
    if any(now[k]!=env['runtime'][k] for k in ('python','executable','numpy','scipy','sklearn','torch')):raise ValueError('Runtime changed')
    if env['design']!=DESIGN or env['methods']!=list(NAMES) or env['seeds']!=list(SEEDS) or env['partitions']!=list(PARTITIONS):raise ValueError('Plan changed')

def save(path,value):
    if path.exists():raise FileExistsError(path)
    temporary=path.with_suffix(path.suffix+'.part')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temporary.replace(path)

def check_reference(case,reference):
    validate_payload(reference)
    if (reference['config']!=case['config'] or reference['seed']!=case['seed'] or reference['partition']!=case['partition']
            or reference['prepared_directory']!=case['prepared_directory'] or reference['dataset']!='Fashion-MNIST'
            or reference['identity']['core_source_hashes']!=source_hashes()
            or reference['initial_head_digest']!=case['initial_head_digest']):raise ValueError('Reference identity differs')
    current={(r['round'],r['method']):r for r in case['round_records']}
    wanted={(r,m) for r in range(1,case['config']['rounds']+1) for m in ('Local','B')}
    oldrows=[r for r in reference['round_records'] if r['method'] in ('Local','B')]
    oldkeys=[(r['round'],r['method']) for r in oldrows]
    if len(oldkeys)!=len(wanted) or set(oldkeys)!=wanted:raise ValueError('Reference has duplicate or missing rounds')
    expected_rounds=set(range(case['config']['eval_every'],case['config']['rounds']+1,case['config']['eval_every']))|{case['config']['rounds']}
    oldmetrics=[m for m in reference['metrics'] if m['method'] in ('Local','B')]
    oldmetric_keys=[(m['round'],m['method']) for m in oldmetrics]
    if len(oldmetric_keys)!=2*len(expected_rounds) or set(oldmetric_keys)!={(r,m) for r in expected_rounds for m in ('Local','B')}:
        raise ValueError('Reference has duplicate or missing evaluations')
    count=0
    for old in oldrows:
        method='Aggregate' if old['method']=='B' else 'Local';new=current[(old['round'],method)]
        if new['head_digest_after_public']!=old['head_digest_after_public'] or new['traffic']!=old['traffic']:raise ValueError('Aggregate/Local differs from accepted reference trajectory')
        count+=1
    if count!=2*case['config']['rounds']:raise ValueError('Incomplete reference')
    for old in oldmetrics:
        method='Aggregate' if old['method']=='B' else 'Local'
        new=next(m for m in case['metrics'] if m['round']==old['round'] and m['method']==method)
        expected_metric=dict(old,method=method)
        if expected_metric!=new:raise ValueError('Reference evaluation differs')
    for method,oldmethod in [('Aggregate','B'),('Local','Local')]:
        if case['summary'][method]['traffic']!=reference['summary'][oldmethod]['traffic']:raise ValueError('Reference total traffic differs')
    return dict(checked=True,round_method_pairs_checked=count,reference_payload_sha256=reference['payload_sha256'])

def check_case(case,cfg,seed,partition,env,directory,truth,reference=None):
    validate_payload(case)
    if (case['identity']!=env or case['config']!=cfg.json() or case['seed']!=seed or case['partition']!=partition
            or case['dataset']!='Fashion-MNIST' or case['prepared_directory']!=str(directory.resolve())
            or case['partition_audit']!=load_json(directory/'partition.json') or set(case['summary'])!=set(NAMES)):
        raise ValueError('Case identity mismatch')
    n=len(cfg.dimensions);e=cfg.samples*cfg.degree//2;rr=case['round_records']
    checkpoints=sorted({1,cfg.rounds,*range(cfg.eval_every,cfg.rounds+1,cfg.eval_every)})
    keys=[(r['round'],r['method']) for r in rr]
    if len(keys)!=4*cfg.rounds or set(keys)!={(r,m) for r in range(1,cfg.rounds+1) for m in NAMES}:raise ValueError('Incomplete rounds')
    tr=case['target_records'];tk=[(r['round'],r['method']) for r in tr]
    if len(tk)!=3*cfg.rounds or set(tk)!={(r,m) for r in range(1,cfg.rounds+1) for m in TARGETS}:raise ValueError('Incomplete target log')
    target_index={}
    for r in tr:
        if r['clients']!=n or r['edges']!=e:raise ValueError('Target shape mismatch')
        validate_record(r,seed,truth);target_index[(r['round'],r['method'])]=r
    diag=case['diagnostics'];dk=[(r['round'],r['anchor'],r['client'],r['target_kind']) for r in diag]
    expected={(r,m,c,k) for r in checkpoints for m in NAMES for c in range(n) for k in TARGETS}
    if len(dk)!=len(expected) or set(dk)!=expected:raise ValueError('Incomplete gradient probes')
    for r in diag:
        if r['public_weight']!=cfg.public_weight or r['width']!=cfg.dimensions[r['client']]:raise ValueError('Probe identity differs')
        for k,v in r.items():
            if isinstance(v,float) and not math.isfinite(v):raise ValueError('Nonfinite diagnostic')
        if abs(r['public_grad_norm_weighted']-cfg.public_weight*r['public_grad_norm_raw'])>1e-12:raise ValueError('Wrong gradient weight')
    groups={}
    for r in diag:groups.setdefault((r['round'],r['anchor'],r['client']),[]).append(r)
    for rows in groups.values():
        for key in ('student_snapshot_digest','private_batch_digest','public_edge_batch_digest','private_grad_norm','private_loss'):
            if any(r[key]!=rows[0][key] for r in rows):raise ValueError('Counterfactual probes use different snapshots/batches')
    private_steps=sum((size+cfg.private_batch-1)//cfg.private_batch for size in case['partition_audit']['diagnostics']['client_counts'])*cfg.private_epochs
    public_steps=n*cfg.public_epochs*((e+cfg.public_edge_batch-1)//cfg.public_edge_batch)
    for row in rr:
        if row['private_optimizer_steps']!=private_steps or row['public_optimizer_steps']!=(0 if row['method']=='Local' else public_steps):raise ValueError('Unequal training budgets')
        for phase in ('private','generation','exchange','public','pipeline'):
            if not math.isfinite(row[phase+'_seconds']) or row[phase+'_seconds']<0:raise ValueError('Invalid timing')
        if abs(row['pipeline_seconds']-sum(row[k+'_seconds'] for k in ('private','generation','exchange','public')))>1e-8:raise ValueError('Diagnostic phase sum differs')
        if row['method']=='Local':
            if row['traffic'] or row['teacher_forward_endpoints'] or row['student_forward_endpoints'] or row['applied_targets_digest'] is not None:raise ValueError('Local collaborated')
            if row['head_digest_before_public']!=row['head_digest_after_public']:raise ValueError('Local public update')
        else:
            if row['teacher_forward_endpoints']!=n*cfg.samples or row['applied_targets_digest']!=target_index[(row['round'],row['method'])]['applied_targets_digest']:raise ValueError('Target/prediction log differs')
        if row['method']=='Self' and row['traffic']:raise ValueError('Self-only uses cross-client traffic')
    mk=[(m['round'],m['method']) for m in case['metrics']]
    if len(mk)!=4*len(checkpoints) or set(mk)!={(r,m) for r in checkpoints for m in NAMES}:raise ValueError('Incomplete evaluations')
    for m in case['metrics']:
        if [c['client'] for c in m['clients']]!=list(range(n)):raise ValueError('Client metrics missing')
        for key in ('acc','nmi','ari'):
            if not math.isfinite(m['mean'][key]) or abs(m['mean'][key]-np.mean([c[key] for c in m['clients']]))>1e-12:raise ValueError('Invalid mean metric')
    for method,s in case['summary'].items():
        rows=[r for r in rr if r['method']==method]
        if abs(s['head_pipeline_seconds']-(s['initialization_seconds']+sum(r['pipeline_seconds'] for r in rows)))>1e-8:raise ValueError('Invalid summary timing')
        if s['final_head_digest']!=rows[-1]['head_digest_after_public'] or s['final_metrics']!=next(m for m in case['metrics'] if m['method']==method and m['round']==cfg.rounds):raise ValueError('Final summary differs')
        traffic=Counter(s['initial_traffic'])
        for row in rows:traffic.update(row['traffic'])
        if dict(traffic)!=s['traffic']:raise ValueError('Invalid traffic total')
    v=case['validation']
    if (v['mismatches']!=0 or v['target_records_checked']!=3*cfg.rounds or v['teacher_relation_entries']!=3*cfg.rounds*n*e
            or v['probe_rows']!=len(diag) or not v['probes_enabled']):raise ValueError('Incorrect validation coverage')
    expected_ref=dict(checked=False) if reference is None else check_reference(case,reference)
    if case['reference_validation']!=expected_ref:raise ValueError('Reference validation metadata differs')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset',choices=('full','smoke'),default='full')
    ap.add_argument('--prepare-device',choices=('cpu','cuda'))
    ap.add_argument('--download',action='store_true');ap.add_argument('--resume',action='store_true')
    ap.add_argument('--cache',type=Path,default=ROOT/'experiments/noniid_clustering/prepared')
    ap.add_argument('--data-dir',type=Path,default=ROOT/'experiments/real_iid/data')
    ap.add_argument('--output',type=Path);ap.add_argument('--reference-results',type=Path)
    args=ap.parse_args();output=(args.output or ROOT/f'experiments/collaboration_mechanism/results_{args.preset}').resolve()
    if args.resume:
        env=load_json(output/'environment.json');environment_check(env);cfg=from_json(env['config'])
        args.cache=Path(env['cache']);args.data_dir=Path(env['data_dir']);print('Resume uses frozen plan and sources',flush=True)
    else:
        if output.exists() and any(output.iterdir()):raise FileExistsError('Use new output or --resume')
        cfg=replace(preset(args.preset),prepare_device=args.prepare_device or ('cuda' if args.preset=='full' else 'cpu'));cfg.validate()
        refroot=args.reference_results or ROOT/f'experiments/noniid_clustering/results_{args.preset}'
        references={}
        for seed in SEEDS:
            for part in PARTITIONS:
                p=refroot/f'{part}_seed_{seed}.json'
                if p.is_file():references[f'{part}_{seed}']=dict(path=str(p.resolve()),sha256=sha(p))
        if args.reference_results and len(references)!=9:raise ValueError('Explicit reference directory requires all 9 cases')
        env=dict(preset=args.preset,config=cfg.json(),design=DESIGN,methods=list(NAMES),seeds=list(SEEDS),partitions=list(PARTITIONS),
            source_hashes=own_sources(),core_source_hashes=source_hashes(),preparation_source_hashes=preparation_sources(),
            runtime=runtime(),cache=str(args.cache.resolve()),data_dir=str(args.data_dir.resolve()),references=references)
        output.mkdir(parents=True,exist_ok=True);save(output/'environment.json',env)
    ensure_data(args.data_dir,args.download)
    cases=[];public_ids={};labels=idx(args.data_dir/'train-labels-idx1-ubyte.gz')
    with threadpool_limits(limits=cfg.threads):
        for seed in env['seeds']:
            order=list(PARTITIONS);shift=seed%3;order=order[shift:]+order[:shift]
            for part in order:
                print(f'{part} seed={seed}: frozen features and four target branches',flush=True)
                marker=output/f'prepared_{part}_seed_{seed}.json'
                if marker.exists():
                    m=load_json(marker);directory=Path(m['path'])
                    if sha(directory/'prepared.json')!=m['metadata_sha256']:raise ValueError('Prepared identity changed')
                else:
                    directory=prepare(args.cache,args.data_dir,cfg,seed,part,download=args.download)
                    save(marker,dict(path=str(directory.resolve()),metadata_sha256=sha(directory/'prepared.json')))
                verify(directory,cfg,seed,part)
                pub=np.load(directory/'public_ids.npy',allow_pickle=False)
                if seed in public_ids and public_ids[seed]!=hashlib.sha256(pub.tobytes()).hexdigest():raise ValueError('Public pool differs across splits')
                public_ids[seed]=hashlib.sha256(pub.tobytes()).hexdigest()
                public_truth=labels[pub[:cfg.samples]]
                from experiments.public_scaling.graphs import make_graph
                from experiments.public_scaling.certification import hard_relations
                truth=hard_relations(public_truth,make_graph(cfg.samples,cfg.degree,seed))
                refmeta=env['references'].get(f'{part}_{seed}');reference=None
                if refmeta:
                    if sha(Path(refmeta['path']))!=refmeta['sha256']:raise ValueError('Reference changed')
                    reference=load_json(refmeta['path'])
                    if reference['config']!=cfg.json():raise ValueError('Reference config differs; use matching prepare device/config')
                p=output/f'{part}_seed_{seed}.json'
                if p.exists():
                    case=load_json(p);check_case(case,cfg,seed,part,env,directory,truth,reference);print('  preserved completed case',flush=True)
                else:
                    result=run(directory,cfg,public_truth=public_truth)
                    case=dict(**result,partition=part,partition_audit=load_json(directory/'partition.json'),identity=env)
                    case['reference_validation']=dict(checked=False) if reference is None else check_reference(case,reference)
                    case=seal_payload(case);check_case(case,cfg,seed,part,env,directory,truth,reference);save(p,case)
                cases.append(case);reports(output,cases)
    done=dict(case_count=len(cases),training_trajectories=len(cases)*4,mismatches=0,
        target_records_checked=sum(c['validation']['target_records_checked'] for c in cases),
        teacher_relation_entries=sum(c['validation']['teacher_relation_entries'] for c in cases),
        gradient_probe_rows=sum(len(c['diagnostics']) for c in cases),
        reference_round_method_pairs=sum(c['reference_validation'].get('round_method_pairs_checked',0) for c in cases),
        files={p.name:sha(p) for p in output.iterdir() if p.is_file() and p.name!='completed.json' and not p.name.endswith('.part')})
    temporary=output/'completed.json.part';temporary.write_text(json.dumps(done,indent=2),encoding='utf-8');temporary.replace(output/'completed.json')
    print(f'Finished: {output/"report.md"}',flush=True)

if __name__=='__main__':main()
