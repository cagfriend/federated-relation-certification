"""Independent-process diagnosis on the previously observed N12 collapse case."""
import argparse
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from threadpoolctl import threadpool_limits
from experiments.client_scaling import run as client_run
from experiments.client_scaling.design import plan as client_plan
from experiments.client_scaling.telemetry import Monitor
from experiments.private_workload.design import spec_from_json
from experiments.public_scaling.data import Prepared, runtime
from experiments.public_budget.student import selected_edges
from experiments.stl10_transfer import data as transfer_data
from experiments.stl10_transfer.engine import run as original_engine
from experiments.stl10_transfer.run import digest, seal, write_new, power_status, check_run
from experiments.stl10_compute.run import TRAJECTORY_KEYS, PRIVATE_ANCHOR_FIELDS
from .engine import drive
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
ARMS = ('private_only', 'public1', 'public2_half')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sources():
    result = client_run.sources()
    for path in DIR.glob('*.py'):
        result[str(path.relative_to(ROOT))] = digest(path)
    result['experiments/collapse_intervention/PREREGISTRATION.md'] = digest(DIR / 'PREREGISTRATION.md')
    return result


def checkpoints(rounds):
    return sorted({p for p in (0, 1, 2, 5, 10, rounds, *range(20, rounds + 1, 20)) if p <= rounds})


def branch_spec(base, arm):
    if arm == 'public1':
        return replace(base, steps=1)
    if arm == 'public2_half':
        return replace(base, config=replace(base.config, public_weight=base.config.public_weight * .5))
    if arm in ('private_only', 'reference2'):
        return base
    raise ValueError('Unknown arm')


def check_environment(env):
    if env['sources'] != sources():
        raise ValueError('Frozen source changed')
    now = runtime()
    for key in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform'):
        if env['runtime'].get(key) != now.get(key):
            raise ValueError('Runtime changed: ' + key)
    if digest(Path(env['prepared']) / 'prepared.json') != env['prepared_metadata_sha256']:
        raise ValueError('Prepared metadata changed')
    if digest(env['anchor_path']) != env['anchor_sha256']:
        raise ValueError('Historical reference changed')


def validate(result, base, anchor, *, sealed=True, expected_arm=None):
    if sealed and result.get('run_sha256') != seal(dict(result))['run_sha256']:
        raise ValueError('Result seal mismatch')
    arm = result['arm']
    if expected_arm is not None and (arm != expected_arm or result.get('seed') != anchor['seed']
                                     or result.get('partition') != anchor['partition']):
        raise ValueError('Arm or source identity differs')
    spec = branch_spec(base, arm)
    cfg = spec.config
    n = len(cfg.dimensions)
    if result['spec'] != spec.json() or result['initial_head_digest'] != anchor['initial_head_digest']:
        raise ValueError('Spec or initialization differs')
    if result['graph_sha256'] != anchor['graph_sha256']:
        raise ValueError('Public graph differs')
    rows = result['round_records']
    if [r['round'] for r in rows] != list(range(1, cfg.rounds + 1)):
        raise ValueError('Round coverage differs')
    expected_steps = 0 if arm == 'private_only' else spec.steps * n
    for row, historical in zip(rows, anchor['round_records']):
        for key in PRIVATE_ANCHOR_FIELDS:
            if row[key] != historical[key]:
                raise ValueError('Private workload differs: ' + key)
        if row['public_optimizer_steps'] != expected_steps or row['public_edges_consumed'] != expected_steps * cfg.public_edge_batch:
            raise ValueError('Actual public workload differs')
        if len(row['received_counts_digests']) != n or any(x != row['committed_counts_digest'] for x in row['received_counts_digests']):
            raise ValueError('Aggregated targets differ across receivers')
        expected_orders = []
        for client in range(n):
            order = np.empty(0, dtype=np.int64) if arm == 'private_only' else selected_edges(spec, anchor['seed'], client, row['round'])
            expected_orders.append(hashlib.sha256(order.astype('<u4').tobytes()).hexdigest())
        if row['public_order_digests'] != expected_orders:
            raise ValueError('Public edge schedule differs')
        if arm == 'private_only':
            if row['public_loss'] is not None or row['student_forward_endpoints'] != 0 or row['public_targets_applied']:
                raise ValueError('Private-only arm applied public training')
            if row['head_digest_after_private'] != row['head_digest_after_public']:
                raise ValueError('Private-only public stage changed heads')
        elif not row['public_targets_applied']:
            raise ValueError('Missing public update')
        for phase in ('private', 'generation', 'exchange', 'public', 'pipeline'):
            value = row[phase + '_seconds']
            if not math.isfinite(value) or value < 0:
                raise ValueError('Invalid time')
    if len(anchor['round_records']) < len(rows):
        raise ValueError('Historical reference is too short')
    if result['final_head_digest'] != rows[-1]['head_digest_after_public']:
        raise ValueError('Final head differs')
    if [m['round'] for m in result['metrics']] != checkpoints(cfg.rounds):
        raise ValueError('Evaluation coverage differs')
    if any(len(m['clients']) != n for m in result['metrics']):
        raise ValueError('Missing client metrics')
    expected_stages = [(0, 'initial')] + [(r, phase) for r in checkpoints(cfg.rounds) if r for phase in ('after_private', 'after_public')]
    if [(s['round'], s['phase']) for s in result['stages']] != expected_stages:
        raise ValueError('Stage observations differ')
    if any([c['client'] for c in s['clients']] != list(range(n)) for s in result['stages']):
        raise ValueError('Missing stage clients')


def check_reference(result, anchor):
    if result['initial_head_digest'] != anchor['initial_head_digest'] or result['graph_sha256'] != anchor['graph_sha256']:
        raise ValueError('Reference initialization differs')
    for row, old in zip(result['round_records'], anchor['round_records']):
        for key in TRAJECTORY_KEYS:
            if row[key] != old[key]:
                raise ValueError('Reference trajectory differs: ' + key)
    if len(result['round_records']) > len(anchor['round_records']):
        raise ValueError('Reference length differs')
    for m in result['metrics']:
        old = next((a for a in anchor['metrics'] if a['round'] == m['round']), None)
        if old is not None and (m['clients'] != old['clients'] or m['mean'] != old['mean']):
            raise ValueError('Reference evaluation differs')


def worker(env, out, arm):
    check_environment(env)
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required')
    base = spec_from_json(env['base_spec'])
    transfer_data.verify(env['prepared'], base.config, env['seed'], env['partition'], fixture=env['fixture'])
    started = time.time()
    with threadpool_limits(limits=1):
        data = Prepared(env['prepared'], base.config, allow_test_fixture=True)
        try:
            result = drive(data, base, arm, observations=True, progress=True)
        finally:
            data.close()
    result.update(seed=env['seed'], partition=env['partition'], prepared_directory=env['prepared'],
                  worker_started_utc=started, worker_ended_utc=time.time())
    result = seal(result)
    validate(result, base, read(out / 'historical_public2.json'), expected_arm=arm)
    write_new(out / 'runs' / f'{arm}.json', result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--source-results', type=Path, default=ROOT / 'experiments/client_scaling/results_full_fixed_total')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', choices=ARMS)
    args = parser.parse_args()
    out = (args.output or DIR / f'results_{args.preset}').resolve()
    if args.worker:
        worker(read(out / 'environment.json'), out, args.worker)
        return
    if args.resume:
        env = read(out / 'environment.json')
        check_environment(env)
        if (out / 'completed.json').exists():
            for name, value in read(out / 'completed.json')['files'].items():
                if digest(out / name) != value:
                    raise ValueError('Completed output changed: ' + name)
            print('Already complete: ' + str(out / 'report.md'))
            return
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Choose a new output or use --resume')
        fixture = args.preset == 'smoke'
        if not fixture and power_status()['ac_line_status'] != 1:
            raise RuntimeError('AC power required')
        if fixture:
            base = client_plan('smoke', 'fixed_total')[-1]
            base = replace(base, config=replace(base.config, rounds=12))
            seed, partition = 1001, 'dirichlet_0.1'
            prepared = transfer_data.prepare(DIR / 'fixture_prepared', DIR / 'fixture_data', base.config, seed, partition, fixture=True)
            with threadpool_limits(limits=1):
                anchor = original_engine(prepared, base, 'B', fixture=True)
            anchor.update(partition=partition, method='B')
            anchor = seal(anchor)
            out.mkdir(parents=True, exist_ok=True)
            write_new(out / 'smoke_reference_source.json', anchor)
            anchor_path = out / 'smoke_reference_source.json'
        else:
            source = args.source_results.resolve()
            source_env = read(source / 'environment.json')
            client_run.check_environment(source_env)
            client_run.verify_completed(source)
            meta = dict(seed=1003, partition='dirichlet_0.1', regime='fixed_total', clients=12, method='B')
            info = read(source / 'inputs' / (client_run.input_key(meta).replace('|', '_') + '.json'))
            prepared = Path(info['path'])
            if digest(prepared / 'prepared.json') != info['metadata_sha256']:
                raise ValueError('Historical cache metadata changed')
            base = spec_from_json(source_env['plan']['fixed_total|12'])
            seed, partition = 1003, 'dirichlet_0.1'
            anchor_path = source / 'runs' / 'fixed_total_N12_dirichlet_0.1_seed_1003_B.json'
            anchor = read(anchor_path)
            client_run.verify_record(anchor, meta, base, prepared, False, False)
            out.mkdir(parents=True, exist_ok=True)
        write_new(out / 'historical_public2.json', anchor)
        env = dict(preset=args.preset, fixture=fixture, seed=seed, partition=partition,
                   base_spec=base.json(), prepared=str(prepared.resolve()),
                   prepared_metadata_sha256=digest(prepared / 'prepared.json'),
                   anchor_path=str(anchor_path.resolve()), anchor_sha256=digest(anchor_path),
                   sources=sources(), runtime=runtime(), started_utc=time.time())
        write_new(out / 'environment.json', env)
    check_environment(env)
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required on resume')
    base = spec_from_json(env['base_spec'])
    anchor = read(out / 'historical_public2.json')
    if anchor != read(env['anchor_path']):
        raise ValueError('Copied historical reference changed')
    invocation = time.time_ns()
    with Monitor(out / f'power_{invocation}.jsonl'):
        transfer_data.verify(env['prepared'], base.config, env['seed'], env['partition'], fixture=env['fixture'])
        if not (out / 'preflight.json').exists():
            print('Checking original two-step trajectory for 3 rounds...', flush=True)
            prefix = replace(base, config=replace(base.config, rounds=3))
            with threadpool_limits(limits=1):
                data = Prepared(env['prepared'], prefix.config, allow_test_fixture=True)
                try:
                    result = drive(data, prefix, 'reference2', observations=False)
                finally:
                    data.close()
            check_reference(result, anchor)
            write_new(out / 'preflight.json', seal(dict(rounds_matched=3, reference=result)))
        else:
            preflight = read(out / 'preflight.json')
            if seal(dict(preflight))['run_sha256'] != preflight['run_sha256']:
                raise ValueError('Preflight changed')
            check_reference(preflight['reference'], anchor)
        results = {}
        for arm in ARMS:
            path = out / 'runs' / f'{arm}.json'
            if not path.exists():
                print('Running: ' + arm, flush=True)
                subprocess.run([sys.executable, '-m', 'experiments.collapse_intervention.run',
                                '--output', str(out), '--worker', arm], cwd=ROOT, check=True)
            else:
                print('Preserved: ' + arm, flush=True)
            result = read(path)
            validate(result, base, anchor, expected_arm=arm)
            results[arm] = result
        if {p.stem for p in (out / 'runs').glob('*.json')} != set(ARMS):
            raise ValueError('Unexpected arm records')
        reports(out, results, anchor)
    check_environment(env)
    write_new(out / 'environment_final.json', dict(**env, ended_utc=time.time(), ended_power=power_status()))
    manifest = {str(p.relative_to(out)): digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json', 'finished.json')}
    write_new(out / 'completed.json', dict(files=manifest, runs=3, reference_preflight_rounds=3, status='complete'))
    write_new(out / 'finished.json', dict(completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
