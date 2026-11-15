"""New-seed confirmation with 54 isolated, balanced B/E/D measurements."""
import argparse
import copy
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.public_scaling.data import runtime
from experiments.quantity_heterogeneity import data
from experiments.private_prior.training import log_prior
from . import engine, fixture
from .design import cases, schedule, spec, filename
from .support import ROOT, read, write, seal, digest, sources

DIR=Path(__file__).resolve().parent
TRAJECTORY=('private_loss','public_loss','private_forward_endpoints','student_forward_endpoints',
            'private_samples_per_client','private_subset_digest','private_subset_pseudo_histograms',
            'private_optimizer_steps','public_optimizer_steps','public_edges_consumed','public_schedule_digest',
            'positive_relation_fraction','committed_counts_digest','received_counts_digests','traffic',
            'head_digest_after_public','teacher_relation_hashes','teacher_positive_fractions')
TRAJECTORY += ('teacher_head_digests','head_digests_after_public','target_digests',
               'private_loss_by_client','public_loss_by_client','private_order_sha256_by_client',
               'public_order_sha256_by_client')


def check_environment(env):
    if env['sources']!=sources() or env['spec']!=spec(env['preset'],env['prepare_device']).json():
        raise ValueError('Frozen source/configuration changed')
    if env['schedule']!=schedule(env['preset']):raise ValueError('Frozen schedule changed')
    now=runtime()
    if any(now.get(k)!=env['runtime'].get(k) for k in ('python','executable','numpy','scipy','sklearn','torch','platform')):
        raise ValueError('Runtime changed')


def prepare_inputs(env,out):
    s=spec(env['preset'],env['prepare_device'])
    for case in cases(env['preset']):
        cid=case['case_id']
        print('Checking/preparing '+cid,flush=True)
        if env['preset']=='smoke':
            path=fixture.prepare(env['cache'],DIR/'fixture_data',s,case['seed'],case['partition'])
        else:
            path=data.prepare(env['cache'],env['data_dir'],s,case['seed'],case['partition'],
                              profile='strong',download=env['download'])
        entry=dict(path=str(path.resolve()),metadata_sha256=digest(path/'prepared.json'))
        if cid in env['inputs'] and env['inputs'][cid]!=entry:raise ValueError('Frozen cache pointer changed')
        for c in (0,3):
            log_prior(np.load(path/f'client_{c}_pseudo.npy',allow_pickle=False),s.config.classes)
        env['inputs'][cid]=entry
        write(out/'environment.json',env)


def normalized_metrics(record):
    result=copy.deepcopy(record['metrics'])
    for m in result:m.pop('method',None)
    return result


def verify(record,case,env,out):
    if record.get('run_sha256')!=seal(dict(record))['run_sha256']:raise ValueError('Record seal mismatch')
    for key in ('seed','partition','method','repeat'):
        if record[key]!=case[key]:raise ValueError('Run identity differs: '+key)
    s=spec(env['preset'],env['prepare_device']);cfg=s.config
    if record['spec']!=s.json() or record['config']!=cfg.json():raise ValueError('Configuration differs')
    entry=env['inputs'][case['case_id']]
    if record['prepared_directory']!=entry['path']:raise ValueError('Cache differs')
    if record['public_client_weights']!=[.125,.5,.5,.125,.5,.5]:raise ValueError('Public LR differs')
    if record['probes_enabled'] or record['validation']['enabled'] or record['diagnostic_records']:
        raise ValueError('Performance run contains oracle/probes')
    rows=record['round_records'];rounds=list(range(1,cfg.rounds+1))
    if [r['round'] for r in rows]!=rounds:raise ValueError('Incomplete rounds')
    expected=[r for r in rounds if r%cfg.eval_every==0 or r==cfg.rounds]
    if [m['round'] for m in record['metrics']]!=expected:raise ValueError('Missing checkpoints')
    if any([c['client'] for c in m['clients']]!=list(range(6)) for m in record['metrics']):
        raise ValueError('Missing evaluation clients')
    summary=record['summary'][case['method']]
    if summary['final_head_digest']!=rows[-1]['head_digest_after_public']:raise ValueError('Final digest differs')
    if summary['final_metrics']!=record['metrics'][-1]:raise ValueError('Final evaluation differs')
    for field in ('private_optimizer_steps','public_optimizer_steps','private_forward_endpoints','student_forward_endpoints'):
        if summary[field]!=sum(r[field] for r in rows):raise ValueError('Work accounting differs')
    if abs(summary['head_pipeline_seconds']-(summary['initialization_seconds']+sum(r['pipeline_seconds'] for r in rows)))>1e-8:
        raise ValueError('Pipeline accounting differs')
    stages=summary['initialization_seconds']+sum(r[k+'_seconds'] for r in rows for k in ('private','generation','exchange','public'))
    if not np.isclose(stages,summary['measured_stage_seconds'],atol=1e-8,rtol=0):
        raise ValueError('Stage accounting differs')
    for row in rows:
        if row['method']!=case['method'] or len(row['teacher_relation_hashes'])!=6 or len(row['teacher_positive_fractions'])!=6:
            raise ValueError('Malformed per-client teacher fields')
        if any(x!=row['committed_counts_digest'] for x in row['received_counts_digests']):raise ValueError('Target mismatch')
        if case['method']=='B' and row['teacher_forward_endpoints']!=cfg.samples*6:raise ValueError('B is not full forward')
    anchor_path=out/'runs'/f"{case['case_id']}_B_repeat0.json"
    if case['method']=='B' and case['repeat']==0:anchor=record
    else:
        anchor=read(anchor_path)
        if anchor.get('run_sha256')!=seal(dict(anchor))['run_sha256']:raise ValueError('Reference seal mismatch')
    for field in ('initial_head_digest','graph_sha256','initial_traffic','probe_manifest'):
        a=anchor['summary']['B']['initial_traffic'] if field=='initial_traffic' else anchor[field]
        b=summary['initial_traffic'] if field=='initial_traffic' else record[field]
        if a!=b:raise ValueError('Reference identity differs: '+field)
    for row,ref in zip(rows,anchor['round_records']):
        for field in TRAJECTORY:
            if row[field]!=ref[field]:raise ValueError('Exact trajectory differs: '+field)
    if normalized_metrics(record)!=normalized_metrics(anchor):raise ValueError('Quality trajectory differs')
    repeat0=out/'runs'/f"{case['case_id']}_{case['method']}_repeat0.json"
    if case['repeat']>0:
        previous=read(repeat0)
        if previous.get('run_sha256')!=seal(dict(previous))['run_sha256']:raise ValueError('Repeat reference seal mismatch')
        for row,ref in zip(rows,previous['round_records']):
            for field in ('teacher_forward_endpoints','certified_edges_before_refresh','client_statistics','persistent_method_array_bytes'):
                if row[field]!=ref[field]:raise ValueError('Method repeat differs: '+field)


def worker(env,out,index):
    check_environment(env)
    case=env['schedule'][index];entry=env['inputs'][case['case_id']]
    if digest(Path(entry['path'])/'prepared.json')!=entry['metadata_sha256']:raise ValueError('Prepared metadata differs')
    started=time.time()
    with threadpool_limits(limits=1):
        record=engine.run(entry['path'],spec(env['preset'],env['prepare_device']),branch='local_lr',
                          method=case['method'],fixture=env['preset']=='smoke',enable_probes=False,
                          validate=False,metrics=True)
    record.update(repeat=case['repeat'],worker_started_utc=started,worker_ended_utc=time.time())
    record=seal(record);verify(record,case,env,out)
    write(out/'runs'/filename(case),record)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset',choices=('full','smoke'),default='full')
    ap.add_argument('--prepare-device',choices=('cpu','cuda'))
    ap.add_argument('--download',action='store_true')
    ap.add_argument('--data-dir',type=Path,default=ROOT/'experiments/stl10_transfer/data')
    ap.add_argument('--output',type=Path)
    ap.add_argument('--cache',type=Path,default=DIR/'prepared')
    ap.add_argument('--resume',action='store_true')
    ap.add_argument('--worker',type=int,help=argparse.SUPPRESS)
    args=ap.parse_args();out=(args.output or DIR/('results_'+args.preset)).resolve()
    if args.worker is not None:
        worker(read(out/'environment.json'),out,args.worker);return
    device=args.prepare_device or ('cuda' if args.preset=='full' else 'cpu')
    if args.resume:
        env=read(out/'environment.json')
        if args.preset!=env['preset'] or (args.prepare_device and device!=env['prepare_device']):raise ValueError('Resume settings differ')
        check_environment(env)
    else:
        if out.exists() and any(out.iterdir()):raise FileExistsError('Use --resume or a new output')
        env=dict(preset=args.preset,prepare_device=device,spec=spec(args.preset,device).json(),
                 sources=sources(),runtime=runtime(),schedule=schedule(args.preset),inputs={},
                 cache=str(args.cache.resolve()),data_dir=str(args.data_dir.resolve()),download=args.download)
    out.mkdir(parents=True,exist_ok=True);write(out/'environment.json',env)
    prepare_inputs(env,out)
    records=[]
    for i,case in enumerate(env['schedule']):
        path=out/'runs'/filename(case)
        if not path.exists():
            print(f"Running {i+1}/{len(env['schedule'])}: {path.name}",flush=True)
            subprocess.run([sys.executable,'-m','experiments.private_prior_confirmation.run','--output',str(out),'--worker',str(i)],cwd=ROOT,check=True)
        record=read(path);verify(record,case,env,out);records.append((case,record))
    wanted={filename(c) for c in env['schedule']}
    if {p.name for p in (out/'runs').glob('*.json')}!=wanted:raise ValueError('Unexpected result files')
    check_environment(env)
    for case in cases(env['preset']):
        entry=env['inputs'][case['case_id']]
        if digest(Path(entry['path'])/'prepared.json')!=entry['metadata_sha256']:raise ValueError('Cache identity changed')
    from .report import report
    report(out,records,smoke=env['preset']=='smoke')
    write(out/'completed.json',dict(runs=len(records),files={p.relative_to(out).as_posix():digest(p)
        for p in sorted(out.rglob('*')) if p.is_file() and p.name not in ('completed.json','finished.json')}))
    write(out/'finished.json',dict(completed_manifest_sha256=digest(out/'completed.json')))
    print('Finished: '+str(out),flush=True)


if __name__=='__main__':main()
