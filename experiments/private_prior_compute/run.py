"""Frozen B/E/D comparisons on the verified private-prior trajectory."""
import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.private_prior import run as prior_run
from experiments.private_prior import engine as prior_engine
from experiments.private_prior.fixture import prepare as fixture_prepare
from experiments.private_prior.training import log_prior
from experiments.public_scaling.data import runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.quantity_heterogeneity import data
from experiments.stl10_transfer.run import digest, seal, write_new
from . import engine
from .design import CASES, METHODS, spec, schedule, filename
from .report import report

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).resolve().parent
read = prior_run.read
TRAJECTORY = ('private_loss','public_loss','private_forward_endpoints','student_forward_endpoints',
              'private_samples_per_client','private_subset_digest','private_subset_pseudo_histograms',
              'private_optimizer_steps','public_optimizer_steps','public_edges_consumed','public_schedule_digest',
              'positive_relation_fraction','committed_counts_digest','received_counts_digests',
              'traffic','head_digest_after_public')


def sources():
    result = prior_run.sources()
    for p in sorted(DIR.glob('*.py')):
        result[str(p.relative_to(ROOT))] = digest(p)
    result[str((DIR/'PREREGISTRATION.md').relative_to(ROOT))] = digest(DIR/'PREREGISTRATION.md')
    return result


def check_environment(env):
    if env['sources'] != sources() or env['spec'] != spec(env['preset']).json():
        raise ValueError('Frozen source/configuration changed')
    if env['schedule'] != schedule() or env['memory_schedule'] != (schedule(True) if env['memory_audit'] else []):
        raise ValueError('Frozen schedule changed')
    now = runtime()
    if any(env['runtime'].get(k)!=now.get(k) for k in ('python','executable','numpy','scipy','sklearn','torch','platform')):
        raise ValueError('Runtime changed')


def inputs(env,out):
    preset = env['preset']
    cfg = spec(preset)
    history = ROOT/'experiments/private_prior/results_full'
    if preset == 'full':
        old = read(history/'environment.json')
        prior_run.environment_check(old)
        completed = read(history/'completed.json')
        if read(history/'finished.json')['completed_manifest_sha256'] != digest(history/'completed.json'):
            raise ValueError('Historical completion seal mismatch')
    for case in CASES:
        cid = case['case_id']
        if preset == 'smoke':
            directory = fixture_prepare(ROOT/'experiments/private_prior/prepared_smoke',
                                        ROOT/'experiments/private_prior/fixture_data',cfg,case['seed'],case['partition'])
            reference = out/'references'/(cid+'.json')
            if not reference.exists():
                with threadpool_limits(limits=1):
                    anchor = prior_engine.run(directory,cfg,branch='local_lr',fixture=True,progress=False)
                write_new(reference,seal(anchor))
        else:
            reference = history/'runs'/(cid+'.json')
            files = {k.replace('\\','/'):v for k,v in completed['files'].items()}
            if files.get('runs/'+reference.name) != digest(reference):
                raise ValueError('Historical B reference changed')
            anchor = read(reference)
            prior_run.verify(anchor,case,old['inputs'][cid],preset,True)
            directory = Path(anchor['prepared_directory'])
        anchor = read(reference)
        if anchor.get('run_sha256') != seal(dict(anchor))['run_sha256']:
            raise ValueError('Anchor seal mismatch')
        data.verify(directory,cfg.config,case['seed'],case['partition'],profile='strong',fixture=preset=='smoke')
        for c in (0,3):
            log_prior(np.load(directory/f'client_{c}_pseudo.npy',allow_pickle=False),10)
        entry = dict(path=str(directory.resolve()),metadata_sha256=digest(directory/'prepared.json'),
                     reference=str(reference.resolve()),reference_sha256=digest(reference))
        if cid in env['inputs'] and env['inputs'][cid] != entry:
            raise ValueError('Frozen input identity changed')
        env['inputs'][cid] = entry
        write_new(out/'environment.json',env)


def verify(record,case,entry,preset):
    name = case['method']
    memory = case['memory']
    if record.get('run_sha256') != seal(dict(record))['run_sha256']:
        raise ValueError('Run seal mismatch')
    if record['method'] != name or record['memory_mode'] != memory:
        raise ValueError('Method/memory identity mismatch')
    cfg = spec(preset)
    if record['config'] != cfg.config.json() or record['spec'] != cfg.json():
        raise ValueError('Run configuration changed')
    if digest(entry['reference']) != entry['reference_sha256']:
        raise ValueError('Frozen reference changed')
    anchor = read(entry['reference'])
    for key in ('seed','partition','dataset','initial_head_digest','graph_sha256','probe_manifest',
                'prepared_directory','public_client_weights'):
        if record[key] != anchor[key]:
            raise ValueError('Anchor identity mismatch: '+key)
    rows, refs = record['round_records'], anchor['round_records']
    if [r['round'] for r in rows] != list(range(1,cfg.config.rounds+1)):
        raise ValueError('Incomplete rounds')
    for r,ref,d in zip(rows,refs,anchor['diagnostic_records']):
        for key in TRAJECTORY:
            if r[key] != ref[key]:
                raise ValueError('Exact trajectory mismatch: '+key)
        if r['method'] != name or r['teacher_relation_hashes'] != [c['teacher_relation_sha256_T1'] for c in d['clients']]:
            raise ValueError('Teacher hard relation mismatch')
        if any(v != r['committed_counts_digest'] for v in r['received_counts_digests']):
            raise ValueError('Received target mismatch')
    summary = record['summary'][name]
    if summary['final_head_digest'] != anchor['summary']['B']['final_head_digest']:
        raise ValueError('Final head differs')
    stages = summary['initialization_seconds']+sum(r[k+'_seconds'] for r in rows for k in ('private','generation','exchange','public'))
    if not np.isclose(stages,summary['measured_stage_seconds'],rtol=0,atol=1e-10):
        raise ValueError('Stage accounting mismatch')
    validation = record['validation']
    if memory:
        if not isinstance(record.get('process_peak_bytes'),int) or record['process_peak_bytes'] <= 0:
            raise ValueError('Memory peak measurement unavailable')
        if record['metrics'] or record['diagnostic_records'] or validation['enabled'] or record['probes_enabled']:
            raise ValueError('Memory replay contains audit/probe/evaluation')
    else:
        normalized = copy.deepcopy(record)
        normalized['summary'] = {'B': normalized['summary'][name]}
        for row in normalized['round_records']:
            row['method'] = 'B'
        for m in normalized['metrics']:
            m['method'] = 'B'
        normalized['summary']['B']['final_metrics']['method'] = 'B'
        normalized = seal(normalized)
        from experiments.local_public_lr.run import verify_record
        # The historical verifier requires full teacher forwards every round.
        # Apply it to B. E/D use the same trajectory/diagnostics anchor and
        # separate method-specific oracle coverage checks below.
        if name == 'B':
            verify_record(normalized,prior_run.meta(case),cfg,
                          dict(path=entry['path'],probe_manifest=anchor['probe_manifest']),preset=='smoke')
        if normalized['metrics'] != anchor['metrics'] or record['diagnostic_records'] != anchor['diagnostic_records']:
            raise ValueError('Quality/probe trajectory differs from historical B')
        expected = cfg.config.rounds*6*cfg.config.samples
        if (not validation['enabled'] or validation['mismatches'] != 0
                or validation['relation_comparisons'] != expected*cfg.config.degree//2
                or validation['candidate_membership_comparisons'] != (0 if name=='B' else expected)):
            raise ValueError('Oracle audit coverage mismatch')


def worker(env,out,index,memory):
    check_environment(env)
    case = (env['memory_schedule'] if memory else env['schedule'])[index]
    entry = env['inputs'][case['case_id']]
    if digest(Path(entry['path'])/'prepared.json') != entry['metadata_sha256']:
        raise ValueError('Prepared metadata changed')
    with threadpool_limits(limits=1):
        record = engine.run(entry['path'],spec(env['preset']),branch='local_lr',method=case['method'],
                            fixture=env['preset']=='smoke',enable_probes=not memory,
                            validate=not memory,metrics=not memory)
    record.update(memory_mode=memory,process_peak_bytes=native_peak_bytes())
    record = seal(record)
    verify(record,case,entry,env['preset'])
    write_new(out/('memory' if memory else 'runs')/filename(case),record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset',choices=('full','smoke'),default='full')
    parser.add_argument('--memory-audit',action='store_true')
    parser.add_argument('--resume',action='store_true')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--worker',type=int,help=argparse.SUPPRESS)
    parser.add_argument('--memory-worker',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    out = (args.output or DIR/('results_'+args.preset)).resolve()
    if args.worker is not None:
        worker(read(out/'environment.json'),out,args.worker,args.memory_worker)
        return
    if args.resume:
        env = read(out/'environment.json')
        if args.preset != env['preset'] or args.memory_audit != env['memory_audit']:
            raise ValueError('Resume preset/memory-audit flag differs')
        check_environment(env)
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Use --resume or a new output')
        env = dict(preset=args.preset,memory_audit=args.memory_audit,spec=spec(args.preset).json(),
                   sources=sources(),runtime=runtime(),schedule=schedule(),
                   memory_schedule=schedule(True) if args.memory_audit else [],inputs={})
    out.mkdir(parents=True,exist_ok=True)
    write_new(out/'environment.json',env)
    inputs(env,out)
    groups = []
    for memory,items in ((False,env['schedule']),(True,env['memory_schedule'])):
        records = []
        for index,case in enumerate(items):
            path = out/('memory' if memory else 'runs')/filename(case)
            if not path.exists():
                print(('Memory: ' if memory else 'Running: ')+path.name,flush=True)
                command = [sys.executable,'-m','experiments.private_prior_compute.run','--output',str(out),
                           '--worker',str(index)]
                if memory:
                    command.append('--memory-worker')
                subprocess.run(command,cwd=ROOT,check=True)
            r = read(path)
            verify(r,case,env['inputs'][case['case_id']],env['preset'])
            records.append((case,r))
        groups.append(records)
    check_environment(env)
    inputs(env,out)
    report(out,*groups,smoke=env['preset']=='smoke')
    write_new(out/'completed.json',dict(runs=len(groups[0]),memory_runs=len(groups[1]),files={
        p.relative_to(out).as_posix():digest(p) for p in sorted(out.rglob('*'))
        if p.is_file() and p.name not in ('completed.json','finished.json')}))
    write_new(out/'finished.json',dict(completed_manifest_sha256=digest(out/'completed.json')))
    print('Finished: '+str(out),flush=True)


if __name__ == '__main__':
    main()
