"""Frozen STL-10 long-horizon validation runner. Each trajectory is its own process."""
import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from pathlib import Path

from threadpoolctl import threadpool_limits

from experiments.public_scaling.data import runtime as core_runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.private_workload.design import spec_from_json
from experiments.stl10_transfer import data as transfer_data
from experiments.stl10_transfer.design import plan as transfer_plan
from experiments.stl10_transfer.run import check_environment as check_transfer_environment
from experiments.stl10_transfer.run import power_status

from .design import PARTITIONS, checkpoints, filename, plan, schedule
from .engine import run as engine_run
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
PRIVATE_ANCHOR_FIELDS = ('private_subset_digest', 'private_samples_per_client',
                         'private_subset_pseudo_histograms', 'private_optimizer_steps',
                         'private_forward_endpoints')


def digest(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def frozen_sources():
    folders = ['stl10_longrun', 'stl10_transfer', 'stl10_diagnostics', 'public_scaling',
               'private_workload', 'public_budget', 'noniid_clustering']
    out = {}
    for folder in folders:
        for p in sorted((ROOT / 'experiments' / folder).glob('*.py')):
            out[str(p.relative_to(ROOT))] = digest(p)
    out['experiments/stl10_longrun/PREREGISTRATION.md'] = digest(DIR / 'PREREGISTRATION.md')
    out['experiments/stl10_transfer/PREREGISTRATION.md'] = digest(ROOT / 'experiments/stl10_transfer/PREREGISTRATION.md')
    return out


def write_new(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_suffix(p.suffix + '.part')
    t.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    t.replace(p)


def seal(r):
    r.pop('run_sha256', None)
    r['run_sha256'] = hashlib.sha256(json.dumps(r, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return r


def check_environment(env):
    if env['source_hashes'] != frozen_sources():
        raise ValueError('Frozen source changed')
    now = core_runtime()
    if any(env['runtime'].get(k) != now.get(k) for k in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform')):
        raise ValueError('Runtime changed')
    if env['plan'] != [s.json() for s in plan(env['preset'], env.get('prepare_device'))]:
        raise ValueError('Frozen plan changed')


def check_run(r, meta, spec, prepared):
    if r.get('run_sha256') != hashlib.sha256(json.dumps({k: v for k, v in r.items() if k != 'run_sha256'},
                                                        sort_keys=True, separators=(',', ':')).encode()).hexdigest():
        raise ValueError('Run seal mismatch')
    for k, v in [('seed', meta['seed']), ('partition', meta['partition']), ('method', 'B'),
                 ('case_id', meta['case_id']), ('public_steps', meta['steps'])]:
        if r.get(k) != v:
            raise ValueError(f'Run identity mismatch: {k}')
    if r['spec'] != spec.json() or r['config'] != spec.config.json() or r['prepared_directory'] != str(Path(prepared).resolve()):
        raise ValueError('Run spec/cache mismatch')
    cfg = spec.config
    rr = r['round_records']
    if [x['round'] for x in rr] != list(range(1, cfg.rounds + 1)):
        raise ValueError('Incomplete round coverage')
    n = len(cfg.dimensions)
    for x in rr:
        if x['public_optimizer_steps'] != n * spec.steps:
            raise ValueError('Public step count differs from frozen tier')
        for phase in ('private', 'generation', 'exchange', 'public', 'pipeline'):
            if not math.isfinite(x[phase + '_seconds']) or x[phase + '_seconds'] < 0:
                raise ValueError('Invalid timing')
    if [c['round'] for c in r['checkpoints']] != checkpoints(cfg.rounds):
        raise ValueError('Checkpoint set differs from frozen design')
    if r['checkpoints'][-1]['round'] != cfg.rounds or r['summary']['B']['final_metrics'] != r['checkpoints'][-1]['mean']:
        raise ValueError('Final checkpoint differs')
    if r['summary']['B']['final_head_digest'] != rr[-1]['head_digest_after_public']:
        raise ValueError('Final digest differs')
    return True


def check_anchor(r, anchor):
    """Exactness anchor against the historical step-8 B run (full preset only)."""
    if r['initial_head_digest'] != anchor['initial_head_digest']:
        raise ValueError('Initial head digest differs from historical step-8 B run')
    if r['graph_sha256'] != anchor['graph_sha256']:
        raise ValueError('Graph differs from historical step-8 B run')
    for field in PRIVATE_ANCHOR_FIELDS:
        if [x[field] for x in r['round_records']] != [x[field] for x in anchor['round_records']]:
            raise ValueError(f'Private workload field differs from anchor: {field}')
    return True


def load_anchor(source, partition, seed):
    case = transfer_plan('full')[-1].case_id
    path = Path(source) / 'runs' / f'{partition}_{case}_seed_{seed}_B.json'
    return json.loads(path.read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset', choices=('full', 'smoke'), default='full')
    ap.add_argument('--source-results', type=Path,
                    default=ROOT / 'experiments' / 'stl10_transfer' / 'results_full')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--cache', type=Path, default=DIR / 'prepared')
    ap.add_argument('--data-dir', type=Path, default=DIR / 'data')
    ap.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--worker-seed', type=int, help=argparse.SUPPRESS)
    ap.add_argument('--worker-partition', choices=PARTITIONS, help=argparse.SUPPRESS)
    ap.add_argument('--worker-case', help=argparse.SUPPRESS)
    a = ap.parse_args()
    out = (a.output or DIR / f'results_{a.preset}').resolve()
    runs_dir = out / 'runs'

    if a.worker:
        env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
        check_environment(env)
        spec = next(spec_from_json(x) for x in env['plan'] if spec_from_json(x).case_id == a.worker_case)
        prepared = Path(env['prepared'][f'{a.worker_seed}|{a.worker_partition}']['path'])
        if digest(prepared / 'prepared.json') != env['prepared'][f'{a.worker_seed}|{a.worker_partition}']['metadata_sha256']:
            raise ValueError('Prepared metadata changed')
        t = time.perf_counter()
        with threadpool_limits(limits=spec.config.threads):
            r = engine_run(prepared, spec, fixture=env['fixture'])
        meta = dict(seed=a.worker_seed, partition=a.worker_partition, case_id=spec.case_id, steps=spec.steps)
        r.update(seed=a.worker_seed, partition=a.worker_partition, method='B', steps=spec.steps,
                 worker_wall_seconds=time.perf_counter() - t, process_peak_bytes=native_peak_bytes())
        r = seal(r)
        check_run(r, meta, spec, prepared)
        write_new(runs_dir / filename(meta), r)
        return

    if a.resume:
        env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
        check_environment(env)
        a.cache = Path(env['cache'])
        a.data_dir = Path(env['data_dir'])
        source = Path(env['source_results'])
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Output exists; use --resume or a new --output')
        specs = plan(a.preset)
        fixture = a.preset == 'smoke'
        source = a.source_results.resolve()
        prepared = {}
        if fixture:
            for seed in (1001,):
                for part in PARTITIONS:
                    p = transfer_data.prepare(a.cache, a.data_dir, specs[-1].config, seed, part, fixture=True)
                    prepared[f'{seed}|{part}'] = dict(path=str(p.resolve()), metadata_sha256=digest(p / 'prepared.json'))
        else:
            transfer_env = json.loads((source / 'environment.json').read_text(encoding='utf-8'))
            check_transfer_environment(transfer_env)
            for seed in (1002, 1003):
                for part in PARTITIONS:
                    marker = json.loads((source / f'prepared_{part}_seed_{seed}.json').read_text(encoding='utf-8'))
                    p = Path(marker['path'])
                    if digest(p / 'prepared.json') != marker['metadata_sha256']:
                        raise ValueError('Prepared metadata changed')
                    prepared[f'{seed}|{part}'] = dict(path=str(p.resolve()), metadata_sha256=marker['metadata_sha256'])
        env = dict(preset=a.preset, prepare_device=specs[0].config.prepare_device,
                   plan=[s.json() for s in specs], fixture=fixture, source_results=str(source),
                   cache=str(a.cache.resolve()), data_dir=str(a.data_dir.resolve()),
                   runtime=core_runtime(), source_hashes=frozen_sources(), prepared=prepared,
                   started_power=power_status(), started_utc=time.time(),
                   execution='one trajectory per independent process, serial')
        if a.preset == 'full' and env['started_power']['ac_line_status'] != 1:
            raise RuntimeError('Full run requires verified ACLineStatus=1 at start')
        out.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(exist_ok=True)
        write_new(out / 'environment.json', env)

    specs = [spec_from_json(x) for x in env['plan']]
    invocation_power = power_status()
    if env['preset'] == 'full' and invocation_power['ac_line_status'] != 1:
        raise RuntimeError('Full run and resume require verified ACLineStatus=1')
    write_new(out / f'invocation_{time.time_ns()}.json', dict(utc=time.time(), resume=a.resume, power=invocation_power))

    completed = []
    for meta in schedule(env['preset']):
        spec = next(s for s in specs if s.case_id == meta['case_id'])
        prepared = Path(env['prepared'][f"{meta['seed']}|{meta['partition']}"]['path'])
        target = runs_dir / filename(meta)
        if target.exists():
            r = json.loads(target.read_text(encoding='utf-8'))
            print('Preserved: ' + target.name, flush=True)
        else:
            print('Running: ' + target.name, flush=True)
            cmd = [sys.executable, '-m', 'experiments.stl10_longrun.run', '--output', str(out), '--worker',
                   '--worker-seed', str(meta['seed']), '--worker-partition', meta['partition'],
                   '--worker-case', meta['case_id']]
            subprocess.run(cmd, check=True)
            r = json.loads(target.read_text(encoding='utf-8'))
        check_run(r, meta, spec, prepared)
        if not env['fixture']:
            check_anchor(r, load_anchor(env['source_results'], meta['partition'], meta['seed']))
        completed.append((meta, r))

    expected = schedule(env['preset'])
    if len(completed) != len(expected) or {p.name for p in runs_dir.glob('*.json')} != {filename(m) for m in expected}:
        raise ValueError('Run matrix is incomplete or has unexpected files')
    verdict = reports(out, completed, fixture=env['fixture'], preset=env['preset'])
    check_environment(env)
    env['ended_power'] = power_status()
    env['ended_utc'] = time.time()
    env['power_monitoring'] = 'start/end snapshots only; intermediate changes are unobserved'
    write_new(out / 'environment_final.json', env)
    manifest = {str(x.relative_to(out)): digest(x) for x in sorted(out.rglob('*'))
                if x.is_file() and x.name not in ('completed.json', 'finished.json')}
    write_new(out / 'completed.json', dict(files=manifest, count=len(completed),
                                           selected_steps=verdict['selected_steps'],
                                           finished_utc=env['ended_utc']))
    write_new(out / 'finished.json', dict(status='complete', expected_runs=len(expected),
                                          completed_runs=len(completed),
                                          completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
