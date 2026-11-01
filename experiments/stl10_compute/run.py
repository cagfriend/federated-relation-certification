"""Frozen STL-10 step-2 B/E/D compute runner. Each method is its own process."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from threadpoolctl import threadpool_limits

from experiments.public_scaling.data import runtime as core_runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.private_workload.design import spec_from_json
from experiments.stl10_longrun.design import plan as longrun_plan
from experiments.stl10_longrun.run import check_run as longrun_check_run
from experiments.stl10_transfer import data as transfer_data
from experiments.stl10_transfer.design import plan as transfer_plan
from experiments.stl10_transfer.engine import run as engine_run
from experiments.stl10_transfer.run import check_environment as check_transfer_environment
from experiments.stl10_transfer.run import check_run, digest, power_status, seal, write_new

from .design import ANCHORED_SEEDS, METHODS, PARTITIONS, filename, plan, schedule
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
TRAJECTORY_KEYS = ('head_digest_after_public', 'public_schedule_digest', 'public_optimizer_steps',
                   'student_forward_endpoints', 'public_edges_consumed', 'committed_counts_digest',
                   'received_counts_digests', 'private_loss', 'public_loss', 'private_subset_digest',
                   'private_samples_per_client', 'private_subset_pseudo_histograms',
                   'private_optimizer_steps', 'private_forward_endpoints', 'positive_relation_fraction',
                   'traffic')
PRIVATE_ANCHOR_FIELDS = ('private_subset_digest', 'private_samples_per_client',
                         'private_subset_pseudo_histograms', 'private_optimizer_steps',
                         'private_forward_endpoints')
CLIENT_METRIC_FIELDS = ('acc', 'nmi', 'ari', 'occupied_clusters', 'largest_cluster_fraction', 'cluster_counts')


def frozen_sources():
    folders = ['stl10_compute', 'stl10_longrun', 'stl10_transfer', 'stl10_diagnostics',
               'public_scaling', 'private_workload', 'public_budget', 'noniid_clustering']
    out = {}
    for folder in folders:
        for p in sorted((ROOT / 'experiments' / folder).glob('*.py')):
            out[str(p.relative_to(ROOT))] = digest(p)
    for pkg in ('stl10_compute', 'stl10_transfer', 'stl10_longrun'):
        out[f'experiments/{pkg}/PREREGISTRATION.md'] = digest(ROOT / 'experiments' / pkg / 'PREREGISTRATION.md')
    return out


def check_environment(env):
    if env['source_hashes'] != frozen_sources():
        raise ValueError('Frozen source changed')
    now = core_runtime()
    if any(env['runtime'].get(k) != now.get(k) for k in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform')):
        raise ValueError('Runtime changed')
    if env['plan'] != [s.json() for s in plan(env['preset'], env.get('prepare_device'))]:
        raise ValueError('Frozen plan changed')


def check_anchor8(record, anchor):
    if record['initial_head_digest'] != anchor['initial_head_digest'] or record['graph_sha256'] != anchor['graph_sha256']:
        raise ValueError('Initial head or graph differs from step-8 anchor')
    for field in PRIVATE_ANCHOR_FIELDS:
        if [x[field] for x in record['round_records']] != [x[field] for x in anchor['round_records']]:
            raise ValueError(f'Private workload field differs from step-8 anchor: {field}')


def check_anchor_longrun(record, anchor):
    mine = [{k: row[k] for k in TRAJECTORY_KEYS} for row in record['round_records']]
    theirs = [{k: row[k] for k in TRAJECTORY_KEYS} for row in anchor['round_records']]
    if mine != theirs:
        raise ValueError('B trajectory differs from longrun step-2 anchor')
    anchor_cps = {c['round']: c for c in anchor['checkpoints']}
    for entry in record['metrics']:
        ref = anchor_cps.get(entry['round'])
        if ref is None:
            continue
        if entry['mean'] != ref['mean']:
            raise ValueError(f"Metric mean differs from longrun anchor at round {entry['round']}")
        for got, want in zip(entry['clients'], ref['clients']):
            if {k: got[k] for k in CLIENT_METRIC_FIELDS} != {k: want[k] for k in CLIENT_METRIC_FIELDS}:
                raise ValueError(f"Client metrics differ from longrun anchor at round {entry['round']}")


def load_verified_anchors(env):
    """Verify historical anchors with their own runners before any run starts."""
    source = Path(env['source_results'])
    prepared = env['prepared']
    transfer_spec = transfer_plan('full')[-1]
    anchors8, anchors_long = {}, {}
    seeds = (1001, 1002, 1003) if not env['fixture'] else (1001,)
    for seed in seeds:
        for part in PARTITIONS:
            prep = Path(prepared[f'{seed}|{part}']['path'])
            a8 = json.loads((source / 'runs' / f'{part}_{transfer_spec.case_id}_seed_{seed}_B.json').read_text(encoding='utf-8'))
            check_run(a8, dict(seed=seed, partition=part, method='B', case_id=transfer_spec.case_id),
                      transfer_spec, prep, env['fixture'])
            anchors8[seed, part] = a8
            if seed in ANCHORED_SEEDS and not env['fixture']:
                long_spec = next(s for s in longrun_plan('full') if s.steps == 2)
                path = Path(env['anchor_results']) / 'runs' / f'{part}_{long_spec.case_id}_seed_{seed}_B.json'
                al = json.loads(path.read_text(encoding='utf-8'))
                longrun_check_run(al, dict(seed=seed, partition=part, case_id=long_spec.case_id, steps=2),
                                  long_spec, Path(al['prepared_directory']))
                anchors_long[seed, part] = al
    return anchors8, anchors_long


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset', choices=('full', 'smoke'), default='full')
    ap.add_argument('--source-results', type=Path, default=ROOT / 'experiments' / 'stl10_transfer' / 'results_full')
    ap.add_argument('--anchor-results', type=Path, default=ROOT / 'experiments' / 'stl10_longrun' / 'results_full')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--cache', type=Path, default=DIR / 'prepared')
    ap.add_argument('--data-dir', type=Path, default=DIR / 'data')
    ap.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--worker-seed', type=int, help=argparse.SUPPRESS)
    ap.add_argument('--worker-partition', choices=PARTITIONS, help=argparse.SUPPRESS)
    ap.add_argument('--worker-case', help=argparse.SUPPRESS)
    ap.add_argument('--worker-method', choices=METHODS, help=argparse.SUPPRESS)
    a = ap.parse_args()
    out = (a.output or DIR / f'results_{a.preset}').resolve()
    runs_dir = out / 'runs'

    if a.worker:
        env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
        check_environment(env)
        spec = next(spec_from_json(x) for x in env['plan'] if spec_from_json(x).case_id == a.worker_case)
        entry = env['prepared'][f'{a.worker_seed}|{a.worker_partition}']
        prepared = Path(entry['path'])
        if digest(prepared / 'prepared.json') != entry['metadata_sha256']:
            raise ValueError('Prepared metadata changed')
        transfer_data.verify(prepared, spec.config, a.worker_seed, a.worker_partition, fixture=env['fixture'])
        t = time.perf_counter()
        with threadpool_limits(limits=spec.config.threads):
            r = engine_run(prepared, spec, a.worker_method, fixture=env['fixture'])
        meta = dict(seed=a.worker_seed, partition=a.worker_partition, method=a.worker_method, case_id=spec.case_id)
        r.update(seed=a.worker_seed, partition=a.worker_partition, method=a.worker_method,
                 worker_wall_seconds=time.perf_counter() - t, process_peak_bytes=native_peak_bytes())
        r = seal(r)
        check_run(r, meta, spec, prepared, env['fixture'])
        write_new(runs_dir / filename(meta), r)
        return

    if a.resume:
        env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
        check_environment(env)
        a.cache = Path(env['cache'])
        a.data_dir = Path(env['data_dir'])
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
            for seed in (1001, 1002, 1003):
                for part in PARTITIONS:
                    marker = json.loads((source / f'prepared_{part}_seed_{seed}.json').read_text(encoding='utf-8'))
                    p = Path(marker['path'])
                    if digest(p / 'prepared.json') != marker['metadata_sha256']:
                        raise ValueError('Prepared metadata changed')
                    prepared[f'{seed}|{part}'] = dict(path=str(p.resolve()), metadata_sha256=marker['metadata_sha256'])
        env = dict(preset=a.preset, prepare_device=specs[0].config.prepare_device,
                   plan=[s.json() for s in specs], fixture=fixture, source_results=str(source),
                   anchor_results=str(a.anchor_results.resolve()),
                   cache=str(a.cache.resolve()), data_dir=str(a.data_dir.resolve()),
                   runtime=core_runtime(), source_hashes=frozen_sources(), prepared=prepared,
                   started_power=power_status(), started_utc=time.time(),
                   execution='one method per independent process, serial')
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
    if env['fixture']:
        # Smoke: anchor against the transfer smoke B runs when they are
        # available at --source-results; otherwise equivalence within
        # triples is the only check.
        anchors8, anchors_long = {}, {}
        marker_spec = transfer_plan('smoke')[-1]
        for seed in (1001,):
            for part in PARTITIONS:
                candidate = Path(env['source_results']) / 'runs' / f'{part}_{marker_spec.case_id}_seed_{seed}_B.json'
                if candidate.exists():
                    prep = Path(env['prepared'][f'{seed}|{part}']['path'])
                    a8 = json.loads(candidate.read_text(encoding='utf-8'))
                    check_run(a8, dict(seed=seed, partition=part, method='B', case_id=marker_spec.case_id),
                              marker_spec, prep, True)
                    anchors8[seed, part] = a8
    else:
        anchors8, anchors_long = load_verified_anchors(env)

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
            cmd = [sys.executable, '-m', 'experiments.stl10_compute.run', '--output', str(out), '--worker',
                   '--worker-seed', str(meta['seed']), '--worker-partition', meta['partition'],
                   '--worker-case', meta['case_id'], '--worker-method', meta['method']]
            subprocess.run(cmd, check=True)
            r = json.loads(target.read_text(encoding='utf-8'))
        check_run(r, meta, spec, prepared, env['fixture'])
        anchor = anchors8.get((meta['seed'], meta['partition']))
        if anchor is not None:
            check_anchor8(r, anchor)
        completed.append((meta, r))

    expected = schedule(env['preset'])
    if len(completed) != len(expected) or {p.name for p in runs_dir.glob('*.json')} != {filename(m) for m in expected}:
        raise ValueError('Run matrix is incomplete or has unexpected files')

    triples = {}
    for meta, r in completed:
        triples.setdefault((meta['partition'], meta['seed']), {})[meta['method']] = r
    for key, group in triples.items():
        if set(group) != set(METHODS):
            raise ValueError(f'Incomplete method triple: {key}')
        base = group['B']
        long_anchor = anchors_long.get(key)
        if long_anchor is not None:
            check_anchor_longrun(base, long_anchor)
        for method in ('E', 'D'):
            other = group[method]
            if other['initial_head_digest'] != base['initial_head_digest'] or other['graph_sha256'] != base['graph_sha256']:
                raise ValueError('Initial state or graph differs across methods')
            if [{k: x[k] for k in TRAJECTORY_KEYS} for x in other['round_records']] != \
               [{k: x[k] for k in TRAJECTORY_KEYS} for x in base['round_records']]:
                raise ValueError(f'Trajectory mismatch in {key}')
            if [{k: v for k, v in q.items() if k != 'method'} for q in other['metrics']] != \
               [{k: v for k, v in q.items() if k != 'method'} for q in base['metrics']]:
                raise ValueError('Quality metrics differ across methods')

    rs = [r for _, r in completed]
    reports(out, rs, fixture=env['fixture'], preset=env['preset'])
    check_environment(env)
    env['ended_power'] = power_status()
    env['ended_utc'] = time.time()
    env['power_monitoring'] = 'start/end snapshots only; intermediate changes are unobserved'
    write_new(out / 'environment_final.json', env)
    manifest = {str(x.relative_to(out)): digest(x) for x in sorted(out.rglob('*'))
                if x.is_file() and x.name not in ('completed.json', 'finished.json')}
    write_new(out / 'completed.json', dict(files=manifest, count=len(rs), triples_verified=len(triples),
                                           mismatches=0,
                                           relation_comparisons=sum(r['validation']['relation_comparisons'] for r in rs),
                                           candidate_membership_comparisons=sum(r['validation']['candidate_membership_comparisons'] for r in rs),
                                           finished_utc=env['ended_utc']))
    write_new(out / 'finished.json', dict(status='complete', expected_runs=len(expected),
                                          completed_runs=len(rs),
                                          completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
