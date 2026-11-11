"""Serial quantity-heterogeneity B/E/D study with resumable workers."""
import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from threadpoolctl import threadpool_limits

from experiments.public_scaling.data import runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.private_workload.design import spec_from_json
from experiments.stl10_transfer.run import digest, seal, write_new, power_status, check_run as check_old_run
from experiments.stl10_compute.run import TRAJECTORY_KEYS
from experiments.lr_client_scaling.run import (
    check_environment as check_p3_environment,
    verify_record as verify_p3_record,
    verify_groups as verify_p3_groups,
    verify_completed as verify_p3_completed,
)
from experiments.client_scaling.telemetry import Monitor
from . import data
from .design import PROFILES, METHODS, PARTITIONS, PROFILE_REGIME, capacities, plan, schedule, filename, input_key
from .engine import run as engine_run
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
IDENTITY = ('seed', 'partition', 'profile', 'regime', 'clients', 'method')


def sources():
    from experiments.lr_client_scaling.run import sources as p3_sources
    values = p3_sources()
    for p in sorted(DIR.glob('*.py')):
        values[str(p.relative_to(ROOT))] = digest(p)
    prereg = DIR / 'PREREGISTRATION.md'
    if prereg.is_file():
        values[str(prereg.relative_to(ROOT))] = digest(prereg)
    return values


def check_environment(env):
    if env['sources'] != sources():
        raise ValueError('Frozen source changed; do not mix versions')
    now = runtime()
    if any(now.get(k) != env['runtime'].get(k) for k in
           ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform')):
        raise ValueError('Runtime changed')
    expected = {p: s.json() for p, s in plan(env['preset'], env['prepare_device']).items()}
    if env['plan'] != expected:
        raise ValueError('Frozen plan changed')
    if env.get('schedule') != schedule(env['preset']):
        raise ValueError('Frozen schedule changed')
    if env.get('memory_schedule') != schedule(env['preset'], memory=True):
        raise ValueError('Frozen memory schedule changed')


def non_time_rows(record):
    return [{k: v for k, v in row.items() if not k.endswith('_seconds')}
            for row in record['round_records']]


def verify_record(record, meta, spec, prepared, memory, fixture):
    if record.get('run_sha256') != seal(dict(record))['run_sha256']:
        raise ValueError('Run seal mismatch')
    if any(record.get(k) != meta[k] for k in IDENTITY):
        raise ValueError('Run identity mismatch')
    if record.get('memory_mode') != memory:
        raise ValueError('Memory identity mismatch')
    if record['spec'] != spec.json() or record['config'] != spec.config.json():
        raise ValueError('Run configuration mismatch')
    if record['prepared_directory'] != str(Path(prepared).resolve()):
        raise ValueError('Prepared directory mismatch')
    if record['dataset'] != ('STL-10 fixture' if fixture else 'STL-10'):
        raise ValueError('Dataset identity mismatch')
    cfg = spec.config
    sizes = list(capacities('smoke' if fixture else 'full', meta['profile']))
    rows = record['round_records']
    if [r['round'] for r in rows] != list(range(1, cfg.rounds + 1)):
        raise ValueError('Round coverage mismatch')
    expected_steps = sum(math.ceil(n / cfg.private_batch) for n in sizes) * cfg.private_epochs
    for row in rows:
        if row['method'] != meta['method'] or row['private_samples_per_client'] != sizes:
            raise ValueError('Private workload differs from registered capacities')
        if row['private_forward_endpoints'] != sum(sizes) * cfg.private_epochs:
            raise ValueError('Private endpoint count mismatch')
        if row['private_optimizer_steps'] != expected_steps:
            raise ValueError('Per-client private batch step count mismatch')
        if row['public_optimizer_steps'] != spec.steps * len(cfg.dimensions):
            raise ValueError('Public step count mismatch')
        if len(row['received_counts_digests']) != len(cfg.dimensions) or any(
                v != row['committed_counts_digest'] for v in row['received_counts_digests']):
            raise ValueError('Received targets mismatch')
        for phase in ('private', 'generation', 'exchange', 'public', 'pipeline'):
            if not math.isfinite(row[phase + '_seconds']) or row[phase + '_seconds'] < 0:
                raise ValueError('Invalid phase timing')
    summary = record['summary'][meta['method']]
    if summary['final_head_digest'] != rows[-1]['head_digest_after_public']:
        raise ValueError('Final head mismatch')
    if summary['private_samples_per_client'] != sizes:
        raise ValueError('Private summary capacity mismatch')
    if abs(summary['head_pipeline_seconds'] - (summary['initialization_seconds'] + sum(r['pipeline_seconds'] for r in rows))) > 1e-8:
        raise ValueError('Head pipeline summary mismatch')
    for phase in ('private', 'generation', 'exchange', 'public'):
        if abs(summary[phase + '_seconds'] - sum(r[phase + '_seconds'] for r in rows)) > 1e-8:
            raise ValueError(f'{phase} summary mismatch')
    for field in ('public_optimizer_steps', 'student_forward_endpoints',
                  'private_optimizer_steps', 'private_forward_endpoints'):
        if summary[field] != sum(r[field] for r in rows):
            raise ValueError(f'{field} summary mismatch')
    if summary['final_metrics'] != (record['metrics'][-1] if record['metrics'] else None):
        raise ValueError('Final metrics summary mismatch')
    if memory:
        val = record['validation']
        if val['enabled'] or val['relation_comparisons'] or val['candidate_membership_comparisons'] or record['metrics'] or record['coverage_records']:
            raise ValueError('Memory run contains audit or evaluation')
    else:
        val = record['validation']
        n = len(cfg.dimensions)
        if not val['enabled'] or val['mismatches'] or val['relation_comparisons'] != cfg.rounds * n * cfg.samples * cfg.degree // 2:
            raise ValueError('Oracle relation audit coverage mismatch')
        if val['candidate_membership_comparisons'] != (0 if meta['method'] == 'B' else cfg.rounds * n * cfg.samples):
            raise ValueError('Oracle candidate audit coverage mismatch')
        expected_metrics = [r for r in range(1, cfg.rounds + 1)
                            if r % cfg.eval_every == 0 or r == cfg.rounds]
        if len(record['coverage_records']) != cfg.rounds or [x['round'] for x in record['coverage_records']] != list(range(1, cfg.rounds + 1)):
            raise ValueError('Evaluation or coverage rows incomplete')
        if [x['round'] for x in record['metrics']] != expected_metrics:
            raise ValueError('Evaluation checkpoint coverage mismatch')
        check_old_run(record, dict(seed=meta['seed'], partition=meta['partition'],
                                   method=meta['method'], case_id=spec.case_id),
                      spec, Path(prepared), fixture)
    return True


def verify_groups(completed):
    groups = {}
    for meta, record in completed:
        key = (meta['profile'], meta['partition'], meta['seed'])
        group = groups.setdefault(key, {})
        if meta['method'] in group:
            raise ValueError('Duplicate method in B/E/D triple')
        group[meta['method']] = record
    for key, group in groups.items():
        if set(group) != set(METHODS):
            raise ValueError(f'Incomplete B/E/D triple: {key}')
        b = group['B']
        for name in ('E', 'D'):
            other = group[name]
            if any(other[field] != b[field] for field in ('initial_head_digest', 'graph_sha256', 'prepared_directory')):
                raise ValueError('Initial state, graph, or prepared cache differs')
            if [{k: r[k] for k in TRAJECTORY_KEYS} for r in other['round_records']] != [{k: r[k] for k in TRAJECTORY_KEYS} for r in b['round_records']]:
                raise ValueError(f'Trajectory mismatch: {key}')
            if [{k: v for k, v in r.items() if k != 'method'} for r in other['metrics']] != [{k: v for k, v in r.items() if k != 'method'} for r in b['metrics']]:
                raise ValueError(f'Evaluation mismatch: {key}')
            for field in ('traffic', 'initial_traffic'):
                if other['summary'][name][field] != b['summary']['B'][field]:
                    raise ValueError('Communication differs across methods')
    return groups


def _validate_equal_anchors(source_results, preset, fixture):
    if fixture:
        return {}, None
    root = Path(source_results)
    verify_p3_completed(root)
    env = json.loads((root / 'environment.json').read_text(encoding='utf-8'))
    check_p3_environment(env)
    finished = json.loads((root / 'finished.json').read_text(encoding='utf-8'))
    if finished.get('status') != 'complete' or finished.get('completed_manifest_sha256') != digest(root / 'completed.json'):
        raise ValueError('P3 finished marker does not seal its completed manifest')
    completed = json.loads((root / 'completed.json').read_text(encoding='utf-8'))
    if completed.get('mismatches') != 0:
        raise ValueError('P3 completed marker reports mismatches')
    jobs = [m for m in schedule(preset) if m['profile'] == 'equal']
    old, frozen = [], {'environment_sha256': digest(root / 'environment.json'),
                       'completed_sha256': digest(root / 'completed.json'),
                       'finished_sha256': digest(root / 'finished.json'), 'runs': {}, 'inputs': {}}
    for meta in jobs:
        path = root / 'runs' / f"fixed_per_client_N6_{meta['partition']}_seed_{meta['seed']}_{meta['method']}.json"
        record = json.loads(path.read_text(encoding='utf-8'))
        old_meta = dict(seed=meta['seed'], partition=meta['partition'], regime='fixed_per_client',
                        clients=6, method=meta['method'])
        old_spec = next(spec_from_json(v) for v in env['plan'].values()
                        if spec_from_json(v).case_id == meta['case_id'] and
                        len(spec_from_json(v).config.dimensions) == 6)
        pointer = json.loads((root / 'inputs' / f"{meta['seed']}_{meta['partition']}_fixed_per_client_6.json").read_text(encoding='utf-8'))
        prepared = Path(pointer['path'])
        if digest(prepared / 'prepared.json') != pointer['metadata_sha256']:
            raise ValueError('P3 prepared cache metadata digest mismatch')
        verify_p3_record(record, old_meta, old_spec, prepared, False, False)
        old.append((old_meta, record))
        frozen['runs'][path.name] = digest(path)
        pointer_path = root / 'inputs' / f"{meta['seed']}_{meta['partition']}_fixed_per_client_6.json"
        frozen['inputs'][pointer_path.name] = dict(pointer_sha256=digest(pointer_path),
            metadata_sha256=pointer['metadata_sha256'], prepared_directory=str(prepared.resolve()))
    verify_p3_groups(old)
    return {(r['seed'], r['partition'], r['method']): r for _, r in old}, frozen


def _compare_equal_anchor(record, meta, anchors):
    old = anchors[(meta['seed'], meta['partition'], meta['method'])]
    if record['initial_head_digest'] != old['initial_head_digest'] or record['graph_sha256'] != old['graph_sha256']:
        raise ValueError('Equal profile anchor initial state or graph differs from P3')
    if non_time_rows(record) != non_time_rows(old):
        raise ValueError('Equal profile anchor non-time rows differ from P3')
    if record['metrics'] != old['metrics']:
        raise ValueError('Equal profile anchor evaluation differs from P3')


def worker(out, job, memory):
    env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
    check_environment(env)
    meta = schedule(env['preset'], memory=memory)[job]
    spec = spec_from_json(env['plan'][meta['profile']])
    entry = env['inputs'][input_key(meta)]
    prepared = Path(entry['path'])
    if digest(prepared / 'prepared.json') != entry['metadata_sha256']:
        raise ValueError('Prepared metadata changed')
    data.verify(prepared, spec.config, meta['seed'], meta['partition'],
                profile=meta['profile'], fixture=env['fixture'])
    power = power_status()
    if not env['fixture'] and power['ac_line_status'] != 1:
        raise RuntimeError('AC power required before every formal worker')
    started = time.time()
    engine_started = time.perf_counter()
    with threadpool_limits(limits=spec.config.threads):
        record = engine_run(prepared, spec, meta['method'], profile=meta['profile'],
                            fixture=env['fixture'], memory=memory, progress=True)
    record.update({k: meta[k] for k in IDENTITY}, memory_mode=memory,
                  process_peak_bytes=native_peak_bytes(), worker_started_utc=started,
                  engine_wall_seconds=time.perf_counter() - engine_started,
                  worker_started_power=power, worker_ended_utc=time.time(), worker_ended_power=power_status())
    record = seal(record)
    verify_record(record, meta, spec, prepared, memory, env['fixture'])
    write_new(out / ('memory' if memory else 'runs') / filename(meta), record)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset', choices=('full', 'smoke'), default='full')
    ap.add_argument('--prepare-device', choices=('cpu', 'cuda'))
    ap.add_argument('--download', action='store_true')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--cache', type=Path, default=DIR / 'prepared')
    ap.add_argument('--data-dir', type=Path, default=ROOT / 'experiments/stl10_transfer/data')
    ap.add_argument('--source-results', type=Path, default=ROOT / 'experiments/lr_client_scaling/results_full_fixed_per_client')
    ap.add_argument('--memory-audit', action='store_true')
    ap.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--job', type=int, help=argparse.SUPPRESS)
    ap.add_argument('--memory-worker', action='store_true', help=argparse.SUPPRESS)
    args = ap.parse_args()
    out = (args.output or DIR / f'results_{args.preset}').resolve()
    if args.worker:
        worker(out, args.job, args.memory_worker)
        return
    if args.resume:
        env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
        check_environment(env)
        args.cache, args.data_dir = Path(env['cache']), Path(env['data_dir'])
        if (out / 'completed.json').exists():
            manifest = json.loads((out / 'completed.json').read_text(encoding='utf-8'))
            for name, expected in manifest['files'].items():
                if digest(out / name) != expected:
                    raise ValueError('Completed result changed: ' + name)
            finished = json.loads((out / 'finished.json').read_text(encoding='utf-8'))
            if finished['completed_manifest_sha256'] != digest(out / 'completed.json'):
                raise ValueError('Finished seal mismatch')
            print('Already complete; manifest verified: ' + str(out / 'report.md'))
            return
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Output exists; use --resume or choose a new output')
        fixture = args.preset == 'smoke'
        specs = plan(args.preset, args.prepare_device)
        pwr = power_status()
        if not fixture and pwr['ac_line_status'] != 1:
            raise RuntimeError('Full run requires verified AC power at start')
        env = dict(preset=args.preset, fixture=fixture,
                   prepare_device=next(iter(specs.values())).config.prepare_device,
                   plan={p: s.json() for p, s in specs.items()},
                   schedule=schedule(args.preset), memory_schedule=schedule(args.preset, memory=True),
                   sources=sources(), runtime=runtime(),
                   cache=str(args.cache.resolve()),
                   data_dir=str((DIR / 'fixture_data' if fixture else args.data_dir).resolve()),
                   source_results=str(args.source_results.resolve()), memory_audit=args.memory_audit,
                   started_power=pwr, started_utc=time.time())
        out.mkdir(parents=True, exist_ok=True)
        write_new(out / 'environment.json', env)

    pwr = power_status()
    if not env['fixture'] and pwr['ac_line_status'] != 1:
        raise RuntimeError('Full run/resume requires verified AC power')
    write_new(out / f'invocation_{time.time_ns()}.json', dict(resume=args.resume, power=pwr, utc=time.time()))
    with Monitor(out / f'power_{time.time_ns()}.jsonl', interval=15):
        anchors, anchor_manifest = _validate_equal_anchors(env['source_results'], env['preset'], env['fixture'])
        if env.get('equal_anchor_sources') not in (None, anchor_manifest):
            raise ValueError('P3 equal-profile source files changed since this run was initialized')
        if anchor_manifest is not None:
            env['equal_anchor_sources'] = anchor_manifest
            write_new(out / 'environment.json', env)
        jobs = schedule(env['preset'])
        inputs = env.get('inputs', {})
        for meta in jobs:
            key = input_key(meta)
            if key in inputs:
                marker = inputs[key]
                prepared = Path(marker['path'])
                if digest(prepared / 'prepared.json') != marker['metadata_sha256']:
                    raise ValueError('Prepared metadata changed')
                data.verify(prepared, spec_from_json(env['plan'][meta['profile']]).config,
                            meta['seed'], meta['partition'], profile=meta['profile'], fixture=env['fixture'])
                continue
            spec = spec_from_json(env['plan'][meta['profile']])
            print(f"Preparing: seed={meta['seed']} {meta['partition']} {meta['profile']}", flush=True)
            prepared = data.prepare(env['cache'], env['data_dir'], spec, meta['seed'], meta['partition'],
                                   profile=meta['profile'], fixture=env['fixture'],
                                   download=args.download and not env['fixture'],
                                   source_results=env['source_results'])
            inputs[key] = dict(path=str(Path(prepared).resolve()), metadata_sha256=digest(prepared / 'prepared.json'))
            env['inputs'] = inputs
            write_new(out / 'environment.json', env)

        completed, memories = [], []
        for memory in ((False, True) if env['memory_audit'] else (False,)):
            target_list = memories if memory else completed
            expected = schedule(env['preset'], memory=memory)
            folder = out / ('memory' if memory else 'runs')
            for job, meta in enumerate(expected):
                spec = spec_from_json(env['plan'][meta['profile']])
                prepared = Path(env['inputs'][input_key(meta)]['path'])
                target = folder / filename(meta)
                if not target.exists():
                    print(('Memory: ' if memory else 'Running: ') + target.name, flush=True)
                    cmd = [sys.executable, '-m', 'experiments.quantity_heterogeneity.run',
                           '--worker', '--job', str(job), '--output', str(out)]
                    if memory:
                        cmd.append('--memory-worker')
                    subprocess.run(cmd, check=True, cwd=ROOT)
                record = json.loads(target.read_text(encoding='utf-8'))
                verify_record(record, meta, spec, prepared, memory, env['fixture'])
                if not memory and meta['profile'] == 'equal' and not env['fixture']:
                    _compare_equal_anchor(record, meta, anchors)
                if memory:
                    reference = next(r for m, r in completed if all(m[k] == meta[k] for k in ('seed','partition','profile','method')))
                    if non_time_rows(record) != non_time_rows(reference) or record['initial_head_digest'] != reference['initial_head_digest']:
                        raise ValueError('Memory trajectory differs from normal run')
                    for field in ('persistent_method_array_bytes', 'initial_traffic', 'traffic'):
                        if record['summary'][meta['method']][field] != reference['summary'][meta['method']][field]:
                            raise ValueError('Memory summary/communication differs: ' + field)
                target_list.append((meta, record))
            if {p.name for p in folder.glob('*.json')} != {filename(m) for m in expected}:
                raise ValueError('Unexpected or missing result files')
        groups = verify_groups(completed)
        if memories:
            verify_groups(memories)
        reports(out, completed, memories, fixture=env['fixture'])
        check_environment(env)
    ended = power_status()
    write_new(out / 'environment_final.json', dict(**env, ended_utc=time.time(), ended_power=ended,
             power_monitoring='15-second parent AC sampling during preparation and methods; no automatic timing exclusions'))
    manifest = {str(p.relative_to(out)): digest(p) for p in sorted(out.rglob('*'))
                if p.is_file() and p.name not in ('completed.json', 'finished.json')}
    write_new(out / 'completed.json', dict(files=manifest, runs=len(completed), memory_runs=len(memories),
             triples=len(groups), mismatches=0))
    write_new(out / 'finished.json', dict(status='complete', completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)



if __name__ == '__main__':
    main()
