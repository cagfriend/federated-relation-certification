"""Serial, independent-process B/E/D client-count study. No formal auto-run."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from threadpoolctl import threadpool_limits
from experiments.public_scaling.data import runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.private_workload.design import spec_from_json
from experiments.stl10_transfer.run import digest, seal, write_new, power_status, check_run as old_check_run
from experiments.stl10_compute.run import TRAJECTORY_KEYS
from experiments.client_scaling import data
from .design import plan, schedule, filename, METHODS
from experiments.client_scaling.engine import run as engine_run
from .report import reports
from experiments.client_scaling.telemetry import Monitor

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
IDENTITY = ('seed', 'partition', 'regime', 'clients', 'method')


def sources():
    from experiments.k_scaling.run import sources as old_sources
    values = old_sources()
    from experiments.client_scaling.run import sources as scaling_sources
    values.update(scaling_sources())
    for p in DIR.glob('*.py'):
        values[str(p.relative_to(ROOT))] = digest(p)
    values['experiments/lr_client_scaling/PREREGISTRATION.md'] = digest(DIR / 'PREREGISTRATION.md')
    return values


def all_specs(preset, regime, device=None):
    if regime != 'fixed_per_client':
        raise ValueError('P3 supports fixed_per_client only')
    return {f'fixed_per_client|{len(s.config.dimensions)}': s for s in plan(preset, regime, device)}


def spec_key(meta):
    return f"{meta['regime']}|{meta['clients']}"


def input_key(meta):
    return f"{meta['seed']}|{meta['partition']}|{spec_key(meta)}"


def check_environment(env):
    if env['sources'] != sources():
        raise ValueError('Frozen source changed; do not mix versions')
    now = runtime()
    if any(now.get(k) != env['runtime'].get(k) for k in
           ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform')):
        raise ValueError('Runtime changed')
    expected = {k: s.json() for k, s in all_specs(env['preset'], env['regime'], env['prepare_device']).items()}
    if env['plan'] != expected:
        raise ValueError('Frozen plan changed')
    if env.get('schedule') != schedule(env['preset'], env['regime']):
        raise ValueError('Frozen schedule changed')
    if env.get('memory_schedule') != schedule(env['preset'], env['regime'], memory=True):
        raise ValueError('Frozen memory schedule changed')


def non_time_rows(record):
    return [{k: v for k, v in row.items() if not k.endswith('_seconds')}
            for row in record['round_records']]


def verify_record(record, meta, spec, prepared, memory, fixture):
    if record.get('run_sha256') != seal(dict(record))['run_sha256']:
        raise ValueError('Run seal mismatch')
    if any(record.get(k) != meta[k] for k in IDENTITY):
        raise ValueError('Run identity mismatch')
    if record['memory_mode'] != memory:
        raise ValueError('Memory identity mismatch')
    if record['spec'] != spec.json() or record['config'] != spec.config.json():
        raise ValueError('Run configuration mismatch')
    if record['prepared_directory'] != str(Path(prepared).resolve()):
        raise ValueError('Prepared directory mismatch')
    if record['dataset'] != ('STL-10 fixture' if fixture else 'STL-10'):
        raise ValueError('Dataset identity mismatch')
    cfg = spec.config
    n = len(cfg.dimensions)
    rows = record['round_records']
    if [r['round'] for r in rows] != list(range(1, cfg.rounds + 1)):
        raise ValueError('Round coverage mismatch')
    sizes = [((cfg.train_limit - cfg.public_pool) // n) +
             (i < (cfg.train_limit - cfg.public_pool) % n) for i in range(n)]
    for row in rows:
        if row['method'] != meta['method'] or row['private_samples_per_client'] != sizes:
            raise ValueError('Private workload mismatch')
        if row['private_forward_endpoints'] != sum(sizes) * cfg.private_epochs:
            raise ValueError('Private endpoint count mismatch')
        if row['private_optimizer_steps'] != sum(math.ceil(x / cfg.private_batch) for x in sizes) * cfg.private_epochs:
            raise ValueError('Private step count mismatch')
        if row['public_optimizer_steps'] != spec.steps * n:
            raise ValueError('Public step count mismatch')
        if len(row['received_counts_digests']) != n or any(v != row['committed_counts_digest'] for v in row['received_counts_digests']):
            raise ValueError('Received targets mismatch')
        for phase in ('private', 'generation', 'exchange', 'public', 'pipeline'):
            if not math.isfinite(row[phase + '_seconds']) or row[phase + '_seconds'] < 0:
                raise ValueError('Invalid timing')
    summary = record['summary'][meta['method']]
    if summary['final_head_digest'] != rows[-1]['head_digest_after_public']:
        raise ValueError('Final head mismatch')
    expected_head = summary['initialization_seconds'] + sum(r['pipeline_seconds'] for r in rows)
    if abs(summary['head_pipeline_seconds'] - expected_head) > 1e-8:
        raise ValueError('Head summary mismatch')
    for phase in ('private', 'generation', 'exchange', 'public'):
        if abs(summary[phase + '_seconds'] - sum(r[phase + '_seconds'] for r in rows)) > 1e-8:
            raise ValueError('Phase summary mismatch')
    if memory:
        val = record['validation']
        if val['enabled'] or val['relation_comparisons'] or val['candidate_membership_comparisons'] or record['metrics'] or record['coverage_records']:
            raise ValueError('Memory run contains audit or evaluation')
    else:
        old_check_run(record, dict(meta, case_id=spec.case_id), spec, Path(prepared), fixture)
        if [m['round'] for m in record['metrics']] != [r for r in range(1, cfg.rounds + 1) if r % cfg.eval_every == 0 or r == cfg.rounds]:
            raise ValueError('Evaluation coverage mismatch')
        if any(len(m['clients']) != n for m in record['metrics']):
            raise ValueError('Evaluation client count mismatch')


def verify_groups(completed):
    groups = {}
    for meta, record in completed:
        key = (meta['regime'], meta['clients'], meta['seed'], meta['partition'])
        group = groups.setdefault(key, {})
        if meta['method'] in group:
            raise ValueError('Duplicate method in triple')
        group[meta['method']] = record
    for key, group in groups.items():
        if set(group) != set(METHODS):
            raise ValueError('Incomplete triple')
        b = group['B']
        for name in ('E', 'D'):
            other = group[name]
            if any(other[f] != b[f] for f in ('initial_head_digest', 'graph_sha256', 'prepared_directory')):
                raise ValueError('Initial state/graph differs')
            if [{k: r[k] for k in TRAJECTORY_KEYS} for r in other['round_records']] != [{k: r[k] for k in TRAJECTORY_KEYS} for r in b['round_records']]:
                raise ValueError('Trajectory mismatch: ' + str(key))
            if [{k: v for k, v in r.items() if k != 'method'} for r in other['metrics']] != [{k: v for k, v in r.items() if k != 'method'} for r in b['metrics']]:
                raise ValueError('Metrics mismatch: ' + str(key))
            for field in ('traffic', 'initial_traffic'):
                if other['summary'][name][field] != b['summary']['B'][field]:
                    raise ValueError('Communication mismatch')
    return groups


def verify_completed(out):
    marker = out / 'completed.json'
    if marker.exists():
        manifest = json.loads(marker.read_text(encoding='utf-8'))['files']
        for name, value in manifest.items():
            if digest(out / name) != value:
                raise ValueError('Completed result changed: ' + name)


def worker(env, out, job, memory):
    check_environment(env)
    meta = schedule(env['preset'], env['regime'], memory=memory)[job]
    spec = spec_from_json(env['plan'][spec_key(meta)])
    marker = json.loads((out / 'inputs' / (input_key(meta).replace('|', '_') + '.json')).read_text(encoding='utf-8'))
    prepared = Path(marker['path'])
    if digest(prepared / 'prepared.json') != marker['metadata_sha256']:
        raise ValueError('Prepared metadata changed')
    started = time.time()
    pwr = power_status()
    if not env['fixture'] and pwr['ac_line_status'] != 1:
        raise RuntimeError('AC power required before each worker')
    with threadpool_limits(limits=spec.config.threads):
        record = engine_run(prepared, spec, meta['method'], fixture=env['fixture'], memory=memory)
    record.update({k: meta[k] for k in IDENTITY})
    record.update(memory_mode=memory, process_peak_bytes=native_peak_bytes(),
                  worker_started_utc=started, worker_ended_utc=time.time(),
                  worker_started_power=pwr, worker_ended_power=power_status())
    record = seal(record)
    verify_record(record, meta, spec, prepared, memory, env['fixture'])
    write_new(out / ('memory' if memory else 'runs') / filename(meta), record)


def execute(env, out, download):
    specs = {k: spec_from_json(v) for k, v in env['plan'].items()}
    prepared = {}
    jobs = schedule(env['preset'], env['regime'])
    for meta in jobs:
        key = input_key(meta)
        if key in prepared:
            continue
        spec = specs[spec_key(meta)]
        marker_path = out / 'inputs' / (key.replace('|', '_') + '.json')
        if marker_path.exists():
            marker = json.loads(marker_path.read_text(encoding='utf-8'))
            path = Path(marker['path'])
            if digest(path / 'prepared.json') != marker['metadata_sha256']:
                raise ValueError('Prepared metadata changed')
            data.verify(path, spec, meta['seed'], meta['partition'], fixture=env['fixture'])
        else:
            started = time.time()
            print('Preparing: ' + key, flush=True)
            path = data.prepare(env['cache'], env['data_dir'], spec, meta['seed'], meta['partition'],
                                fixture=env['fixture'], download=download,
                                source_results=env['source_results'])
            write_new(marker_path, dict(path=str(path.resolve()), metadata_sha256=digest(path / 'prepared.json'),
                                       invocation_started_utc=started, invocation_ended_utc=time.time()))
        prepared[key] = path
    # Equal public IDs/order across all N for each seed/partition.
    import numpy as np
    public_ids = {}
    for meta in jobs:
        ids = np.load(prepared[input_key(meta)] / 'public_ids.npy', allow_pickle=False)
        key = meta['seed'], meta['partition']
        if key in public_ids and not np.array_equal(ids, public_ids[key]):
            raise ValueError('Public selection changed across N/regimes')
        public_ids[key] = ids
    anchors = {}
    completed, memories = [], []
    for memory in ((False, True) if env['memory_audit'] else (False,)):
        expected = schedule(env['preset'], env['regime'], memory=memory)
        for job, meta in enumerate(expected):
            path = out / ('memory' if memory else 'runs') / filename(meta)
            spec = specs[spec_key(meta)]
            if not path.exists():
                print(('Memory: ' if memory else 'Running: ') + path.name, flush=True)
                command = [sys.executable, '-m', 'experiments.lr_client_scaling.run', '--worker', '--job', str(job), '--output', str(out)]
                if memory:
                    command.append('--memory-worker')
                subprocess.run(command, check=True, cwd=ROOT)
            else:
                print('Preserved: ' + path.name, flush=True)
            record = json.loads(path.read_text(encoding='utf-8'))
            verify_record(record, meta, spec, prepared[input_key(meta)], memory, env['fixture'])
            if memory:
                reference = next(r for m, r in completed if all(m[k] == meta[k] for k in IDENTITY))
                if non_time_rows(record) != non_time_rows(reference) or record['initial_head_digest'] != reference['initial_head_digest']:
                    raise ValueError('Memory replay trajectory/counters mismatch')
            (memories if memory else completed).append((meta, record))
            # Stop promptly after a complete triple fails exactness.
            if not memory and (job + 1) % 3 == 0:
                verify_groups(completed[-3:])
        actual = {p.name for p in (out / ('memory' if memory else 'runs')).glob('*.json')}
        if actual != {filename(m) for m in expected}:
            raise ValueError('Unexpected result files')
    groups = verify_groups(completed)
    reports(out, completed, memories, fixture=env['fixture'])
    check_environment(env)
    return len(completed), len(memories), len(groups), 0


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset', choices=('full', 'smoke'), default='full')
    ap.add_argument('--regime', choices=('fixed_per_client',), default='fixed_per_client')
    ap.add_argument('--prepare-device', choices=('cuda', 'cpu'))
    ap.add_argument('--output', type=Path)
    ap.add_argument('--cache', type=Path, default=DIR / 'prepared')
    ap.add_argument('--data-dir', type=Path, default=ROOT / 'experiments/stl10_transfer/data')
    ap.add_argument('--source-results', type=Path, default=ROOT / 'experiments/stl10_transfer/results_full')
    ap.add_argument('--download', action='store_true')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--memory-audit', action='store_true')
    ap.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--memory-worker', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--job', type=int, help=argparse.SUPPRESS)
    a = ap.parse_args()
    out = (a.output or DIR / f'results_{a.preset}_{a.regime}').resolve()
    if a.worker:
        worker(json.loads((out / 'environment.json').read_text(encoding='utf-8')), out, a.job, a.memory_worker)
        return
    os.environ.setdefault('LOKY_MAX_CPU_COUNT', '1')
    if a.resume:
        env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
        check_environment(env)
        verify_completed(out)
        if (out / 'completed.json').exists():
            print('Already complete; manifest verified: ' + str(out / 'report.md'))
            return
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Use --resume or choose a new --output')
        specs = all_specs(a.preset, a.regime, a.prepare_device)
        device = next(iter(specs.values())).config.prepare_device
        fixture = a.preset == 'smoke'
        # Fixture bytes are isolated from real official assets.
        data_dir = DIR / 'fixture_data' if fixture else a.data_dir.resolve()
        env = dict(preset=a.preset, regime=a.regime, prepare_device=device,
                   plan={k: s.json() for k, s in specs.items()}, sources=sources(), runtime=runtime(),
                   schedule=schedule(a.preset, a.regime),
                   memory_schedule=schedule(a.preset, a.regime, memory=True),
                   fixture=fixture, memory_audit=a.memory_audit, cache=str(a.cache.resolve()),
                   data_dir=str(data_dir.resolve()), source_results=str(a.source_results.resolve()),
                   started_utc=time.time(), started_power=power_status())
        if not fixture and env['started_power']['ac_line_status'] != 1:
            raise RuntimeError('AC power required before preparation')
        out.mkdir(parents=True, exist_ok=True)
        write_new(out / 'environment.json', env)
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required on resume')
    invocation = time.time_ns()
    write_new(out / f'invocation_{invocation}.json', dict(utc=time.time(), resume=a.resume, power=power_status()))
    with Monitor(out / f'power_{invocation}.jsonl'):
        runs, memories, groups, anchors = execute(env, out, a.download)
    write_new(out / 'environment_final.json', dict(**env, ended_utc=time.time(), ended_power=power_status(),
              power_monitoring='15 second best-effort AC/time sampling during preparation and methods; no automatic exclusions'))
    manifest = {str(p.relative_to(out)): digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json', 'finished.json')}
    write_new(out / 'completed.json', dict(files=manifest, runs=runs, memory_runs=memories, triples=groups, historical_anchors=anchors, mismatches=0))
    write_new(out / 'finished.json', dict(status='complete', completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
