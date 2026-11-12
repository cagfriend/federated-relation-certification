"""Frozen B-only diagnostic with baseline gate and read-only stage probes."""
from pathlib import Path
import argparse,json,time,sys,subprocess,math,hashlib
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.data import runtime
from experiments.stl10_transfer.run import digest,seal,write_new,power_status
from experiments.client_scaling.telemetry import Monitor
from experiments.public_budget.student import selected_edges,schedule_digest
from experiments.quantity_heterogeneity import run as old_run,data as old_data,engine as old_engine
from .design import plan,cases,schedule,filename,source_key,PROBE_SIZES,PROBE_STREAM,PLAN_COMMIT
from .probes import manifest as probe_manifest
from .engine import run as engine_run
from .report import reports
ROOT=Path(__file__).resolve().parents[2];DIR=Path(__file__).parent


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))


def sources():
    result=old_run.sources()
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
    if r.get('run_sha256')!=seal(dict(r))['run_sha256']:raise ValueError('Run seal mismatch')
    if any(r.get(k)!=meta[k] for k in ('seed','partition','branch','profile')):raise ValueError('Run identity mismatch')
    if r['spec']!=spec.json() or r['config']!=spec.config.json() or r['prepared_directory']!=str(Path(entry['path']).resolve()):raise ValueError('Spec/cache mismatch')
    if r['dataset']!=('STL-10 fixture' if fixture else 'STL-10') or not r['probes_enabled']:raise ValueError('Dataset/probe identity mismatch')
    if r['probe_manifest']!=entry['probe_manifest']:raise ValueError('Probe sample identities changed')
    rows=r['round_records'];diag=r['diagnostic_records'];cfg=spec.config
    wanted=list(range(1,cfg.rounds+1))
    if [x['round'] for x in rows]!=wanted or [x['round'] for x in diag]!=wanted:raise ValueError('Incomplete rounds/probes')
    caps=[10,32,54]*2 if fixture else [100,400,700]*2
    metrics=[i for i in wanted if i%cfg.eval_every==0 or i==cfg.rounds]
    if [m['round'] for m in r['metrics']]!=metrics or any(len(m['clients'])!=6 for m in r['metrics']):raise ValueError('Evaluation coverage mismatch')
    initial=r['initial_diagnostics']['clients']
    if [c['client'] for c in initial]!=list(range(6)) or [c['private_capacity'] for c in initial]!=caps:raise ValueError('Initial capacity mismatch')
    for c,n in zip(initial,caps):
        if sum(c['fixed_pseudo_histogram'])!=n or len(c['fixed_pseudo_histogram'])!=10:raise ValueError('Initial pseudo histogram mismatch')
    previous=[c['head_digest'] for c in initial]
    for row,d in zip(rows,diag):
        if row['private_samples_per_client']!=caps or row['private_forward_endpoints']!=sum(caps)*cfg.private_epochs:raise ValueError('Private budget mismatch')
        if row['private_optimizer_steps']!=sum(math.ceil(n/cfg.private_batch) for n in caps)*cfg.private_epochs:raise ValueError('Private step mismatch')
        if row['public_optimizer_steps']!=(0 if meta['branch']=='private_only' else 12):raise ValueError('Public step mismatch')
        if row['teacher_forward_endpoints']!=cfg.samples*6 or any(v!=row['committed_counts_digest'] for v in row['received_counts_digests']):raise ValueError('Teacher/target mismatch')
        if [c['client'] for c in d['clients']]!=list(range(6)):raise ValueError('Client probe coverage mismatch')
        for c,n in zip(d['clients'],caps):
            client=c['client']
            if c['T0']['head_digest']!=previous[client]:raise ValueError('Stage head continuity mismatch')
            previous[client]=c['T2']['head_digest']
            expected_private=[hashlib.sha256(np.asarray(np.random.default_rng(np.random.SeedSequence(
                [int(meta['seed']),401,client,row['round'],epoch])).permutation(n),dtype='<u8').tobytes()).hexdigest() for epoch in range(cfg.private_epochs)]
            public_order=np.empty(0,dtype=np.uint32) if meta['branch']=='private_only' else selected_edges(spec,meta['seed'],client,row['round'])
            if c['private_order_sha256']!=expected_private or c['public_order_sha256']!=hashlib.sha256(np.asarray(public_order,dtype='<u4').tobytes()).hexdigest():raise ValueError('Actual update-order digest mismatch')
            relhash=c['teacher_relation_sha256_T1']
            if len(relhash)!=64 or any(k not in '0123456789abcdef' for k in relhash) or not 0<=c['positive_relation_fraction_T1']<=1:raise ValueError('Teacher relation diagnostic malformed')
            for stage in ('T0','T1','T2'):
                for domain,count in (('private',n),('public',r['probe_manifest']['probe_size'])):
                    s=c[stage][domain]
                    if len(s['counts'])!=10 or any(v<0 for v in s['counts']) or sum(s['counts'])!=count or s['sample_count']!=count:raise ValueError('Probe count mismatch')
                    if s['occupied_clusters']!=sum(v>0 for v in s['counts']) or s['largest_cluster_fraction']!=max(s['counts'])/count:raise ValueError('Probe summary mismatch')
                if not 0<=c[stage]['private']['fixed_pseudo_fit']<=1:raise ValueError('Invalid fit')
            if meta['branch']=='private_only':
                if c['T1']['head_digest']!=c['T2']['head_digest'] or c['T1']['private']!=c['T2']['private'] or c['T1']['public']!=c['T2']['public']:raise ValueError('Private-only mutated public head')
                if any(c['T2']['public_update_delta'][k]!=0 for k in ('weight_l2','bias_l2','parameter_l2')) or c['public_update_loss'] is not None:raise ValueError('Private-only public update observed')
        if meta['branch']=='private_only' and (row['public_loss'] is not None or row['student_forward_endpoints']!=0 or row['public_edges_consumed']!=0):raise ValueError('Private-only consumed public SGD')
        orders=[np.empty(0,dtype=np.uint32) if meta['branch']=='private_only' else selected_edges(spec,meta['seed'],c,row['round']) for c in range(6)]
        if row['public_schedule_digest']!=schedule_digest(orders):raise ValueError('Public batch order mismatch')
        if meta['branch']!='private_only' and abs(row['public_loss']-sum(c['public_update_loss'] for c in d['clients'])/6)>1e-12:raise ValueError('Actual public loss mismatch')
        if abs(row['private_loss']-sum(c['private_update_loss'] for c in d['clients'])/6)>1e-12 or abs(row['positive_relation_fraction']-sum(c['positive_relation_fraction_T1'] for c in d['clients'])/6)>1e-12:raise ValueError('Actual per-client teacher/loss mismatch')
    summary=r['summary']['B']
    if summary['final_head_digest']!=rows[-1]['head_digest_after_public'] or summary['final_metrics']!=r['metrics'][-1]:raise ValueError('Final summary mismatch')
    for field in ('private_optimizer_steps','private_forward_endpoints','public_optimizer_steps','student_forward_endpoints'):
        if summary[field]!=sum(x[field] for x in rows):raise ValueError('Work accounting mismatch')


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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preset',choices=('full','smoke'),default='full');p.add_argument('--output',type=Path);p.add_argument('--source-results',type=Path,default=ROOT/'experiments/quantity_heterogeneity/results_full');p.add_argument('--cache',type=Path,default=DIR/'prepared');p.add_argument('--resume',action='store_true');p.add_argument('--worker',type=int,help=argparse.SUPPRESS);a=p.parse_args()
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
        env=dict(preset=a.preset,fixture=a.preset=='smoke',plan={b:s.json() for b,s in plan(a.preset).items()},schedule=schedule(a.preset),sources=sources(),runtime=runtime(),source_results=str(a.source_results.resolve()),cache=str(a.cache.resolve()),plan_commit=PLAN_COMMIT,
                 probe_config=dict(stream=PROBE_STREAM,size=PROBE_SIZES[a.preset],selection='sorted local choice without replacement'),started_utc=time.time())
    pwr=power_status()
    if not env['fixture'] and pwr['ac_line_status']!=1:raise RuntimeError('AC power required before start/resume')
    out.mkdir(parents=True,exist_ok=True);write_new(out/'environment.json',env)
    write_new(out/f'invocation_{time.time_ns()}.json',dict(resume=a.resume,utc=time.time(),power=pwr))
    completed=[]
    with Monitor(out/f'power_{time.time_ns()}.jsonl',interval=15):
        references=prepare_inputs(env,out)
        for index,meta in enumerate(env['schedule']):
            path=out/'runs'/filename(meta)
            if not path.exists():
                print('Running: '+path.name,flush=True);subprocess.run([sys.executable,'-m','experiments.low_capacity_diagnostic.run','--output',str(out),'--worker',str(index)],cwd=ROOT,check=True)
            else:print('Preserved: '+path.name,flush=True)
            r=read(path);verify_record(r,meta,plan(env['preset'])[meta['branch']],env['inputs'][meta['case_id']],env['fixture'])
            if meta['branch']=='baseline':baseline_compare(r,references[meta['case_id']])
            completed.append((meta,r))
        if {p.name for p in (out/'runs').glob('*.json')}!={filename(m) for m in env['schedule']}:raise ValueError('Unexpected result files')
        reports(out,completed,references,fixture=env['fixture']);check_environment(env)
    write_new(out/'environment_final.json',dict(**env,ended_utc=time.time(),ended_power=power_status()))
    write_new(out/'completed.json',dict(runs=len(completed),baseline_replays=len(cases(env['preset'])),long_diagnostic_runs=len(completed)-len(cases(env['preset'])),files={str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json','finished.json')}))
    write_new(out/'finished.json',dict(completed_manifest_sha256=digest(out/'completed.json')));print('Finished: '+str(out/'report.md'),flush=True)


if __name__=='__main__':main()
