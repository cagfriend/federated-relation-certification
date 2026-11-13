"""Run and seal only the three remaining local public-LR confirmation cases."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.public_scaling.data import runtime
from experiments.stl10_transfer.run import digest, seal, write_new, power_status
from experiments.client_scaling.telemetry import Monitor
from experiments.quantity_heterogeneity import run as quantity_run, data as quantity_data, engine as quantity_engine
from experiments.low_capacity_diagnostic import run as diagnostic_run
from experiments.local_public_lr import run as local_run
from .design import plan, cases, schedule, filename, input_key, PLAN_COMMIT, client_weights
from .probes import manifest as probe_manifest, PROBE_STREAM
from .engine import run as engine_run
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
PROBE_SIZES = {'full': 512, 'smoke': 32}
IDENTITY = ('case_id', 'seed', 'partition', 'profile', 'method', 'branch')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sources():
    # Freeze both layers of prior implementation and all new source files.
    values = diagnostic_run.sources()
    values.update(local_run.sources())
    for path in sorted(DIR.glob('*.py')):
        values[str(path.relative_to(ROOT))] = digest(path)
    values[str((DIR / 'PREREGISTRATION.md').relative_to(ROOT))] = digest(DIR / 'PREREGISTRATION.md')
    return values


def check_environment(env):
    if env['sources'] != sources():
        raise ValueError('Frozen source closure changed')
    now = runtime()
    for key in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform'):
        if now.get(key) != env['runtime'].get(key):
            raise ValueError('Runtime changed: ' + key)
    if env['plan'] != {b: s.json() for b, s in plan(env['preset']).items()}:
        raise ValueError('Frozen plans changed')
    if env['schedule'] != schedule(env['preset']):
        raise ValueError('Frozen schedule changed')
    if env['plan_commit'] != PLAN_COMMIT:
        raise ValueError('Plan commit changed')
    if env['probe_config'] != dict(stream=PROBE_STREAM, size=PROBE_SIZES[env['preset']],
                                   selection='sorted local choice without replacement'):
        raise ValueError('Probe config changed')
    if env['public_client_weights'] != {'local_lr': client_weights()}:
        raise ValueError('Client learning-rate schedule changed')


def verify_completed(root, checker):
    root = Path(root)
    env = read(root / 'environment.json')
    checker(env)
    completed = read(root / 'completed.json')
    for name, expected in completed['files'].items():
        if digest(root / name) != expected:
            raise ValueError(f'Historical file digest mismatch: {name}')
    finished = read(root / 'finished.json')
    if finished.get('completed_manifest_sha256') != digest(root / 'completed.json'):
        raise ValueError('Historical finished seal mismatch')
    return dict(environment_sha256=digest(root / 'environment.json'),
                completed_sha256=digest(root / 'completed.json'),
                finished_sha256=digest(root / 'finished.json'))


def _history_snapshot(env, include_history):
    if env['fixture']:
        return dict(sources={}, records={}), {}, {}
    qroot = Path(env['source_results'])
    localroot = Path(env['local_history_results'])
    droot = Path(env['diagnostic_results'])
    snapshots = dict(quantity=verify_completed(qroot, quantity_run.check_environment),
                     prior_local=verify_completed(localroot, local_run.check_environment),
                     low_capacity=verify_completed(droot, diagnostic_run.check_environment))
    qenv, lenv, denv = (read(qroot / 'environment.json'), read(localroot / 'environment.json'),
                         read(droot / 'environment.json'))
    refs, low_records, local_records = {}, {}, {}
    for case in cases(env['preset']):
        key = input_key(case)
        try:
            pointer = qenv['inputs'][key]
        except KeyError as exc:
            raise ValueError(f'Historical quantity cache pointer missing: {key}') from exc
        prepared = Path(pointer['path'])
        if digest(prepared / 'prepared.json') != pointer['metadata_sha256']:
            raise ValueError('Quantity prepared metadata digest mismatch')
        spec = quantity_run.plan('full')['strong']
        quantity_data.verify(prepared, spec, case['seed'], case['partition'], profile='strong', fixture=False)
        qmeta = next(m for m in quantity_run.schedule('full')
                     if m['seed'] == case['seed'] and m['partition'] == case['partition']
                     and m['profile'] == 'strong' and m['method'] == 'B')
        ref_path = qroot / 'runs' / quantity_run.filename(qmeta)
        ref = read(ref_path)
        quantity_run.verify_record(ref, qmeta, spec, prepared, False, False)
        if ref.get('run_sha256') != seal(dict(ref))['run_sha256']:
            raise ValueError('Quantity reference run seal mismatch')
        public_ids = np.load(prepared / 'public_ids.npy', allow_pickle=False)[:spec.config.samples]
        expected_probe = probe_manifest(case['seed'], public_ids, PROBE_SIZES['full'])
        refs[case['case_id']] = ref
        snapshots.setdefault('cases', {})[case['case_id']] = dict(
            quantity_cache_metadata_sha256=pointer['metadata_sha256'],
            quantity_run_sha256=digest(ref_path),
            public_ids_sha256=expected_probe['public_ids_sha256'],
            local_probe_indices_sha256=expected_probe['local_indices_sha256'],
            prepared_directory=str(prepared.resolve()))

        # The same cache and probe identity must be shared by earlier local
        # and low-capacity records for this exact case.
        diagnostic_case_id = f"strong_{case['partition']}_seed{case['seed']}"
        diagnostic_pointer = denv['inputs'].get(diagnostic_case_id)
        if diagnostic_pointer is None:
            raise ValueError(f'Low-capacity input pointer missing: {diagnostic_case_id}')
        for name, other in (('low-capacity', diagnostic_pointer),):
            if (Path(other['path']).resolve() != prepared.resolve()
                    or other.get('metadata_sha256') != pointer['metadata_sha256']
                    or other.get('probe_manifest') != expected_probe):
                raise ValueError(f'{name} cache/probe identity differs from quantity input')

    # Validate the archived single-case local run's cache and probe as a
    # historical exploratory reference, without adding it to the new matrix.
    prior_key = '1001|iid|strong'
    prior_pointer = lenv['inputs'].get('strong_iid_seed1001')
    if prior_pointer is None:
        raise ValueError('Prior single-case local input pointer missing')
    q_pointer = qenv['inputs'][prior_key]
    prior_ids = np.load(Path(q_pointer['path']) / 'public_ids.npy', allow_pickle=False)[:plan('full')['local_lr'].config.samples]
    prior_probe = probe_manifest(1001, prior_ids, PROBE_SIZES['full'])
    if (Path(prior_pointer['path']).resolve() != Path(q_pointer['path']).resolve()
            or prior_pointer.get('metadata_sha256') != q_pointer.get('metadata_sha256')
            or prior_pointer.get('probe_manifest') != prior_probe):
        raise ValueError('Prior local cache or probe identity differs from quantity history')

    # Freeze earlier one-case local results as exploratory context only.
    local_case_id = 'strong_iid_seed1001'
    prior_case = next(c for c in local_run.cases('full') if c['case_id'] == local_case_id)
    prior_spec = local_run.plan('full')['baseline']
    prior_entry = lenv['inputs'][local_case_id]
    for branch in ('baseline', 'local_lr'):
        meta = dict(prior_case, branch=branch)
        path = localroot / 'runs' / local_run.filename(meta)
        record = read(path)
        local_run.verify_record(record, meta, prior_spec, prior_entry, False)
        local_records[branch] = record
        snapshots.setdefault('prior_local_records', {})[path.name] = digest(path)

    # Freeze the recorded 40-round baseline and global LR/private-only diagnostics.
    for case in cases('full'):
        old_case = next(c for c in diagnostic_run.cases('full')
                        if c['seed'] == case['seed'] and c['partition'] == case['partition'])
        entry = denv['inputs'][old_case['case_id']]
        for branch in ('baseline', 'low_lr', 'private_only'):
            meta = dict(old_case, branch=branch)
            path = droot / 'runs' / diagnostic_run.filename(meta)
            record = read(path)
            diagnostic_run.verify_record(record, meta, diagnostic_run.plan('full')[branch], entry, False)
            if branch == 'baseline':
                local_run.baseline_compare(record, refs[case['case_id']])
            if record['initial_head_digest'] != refs[case['case_id']]['initial_head_digest'] or record['graph_sha256'] != refs[case['case_id']]['graph_sha256']:
                raise ValueError('Historical low-capacity comparison does not match quantity state')
            low_records[(case['case_id'], branch)] = record
            snapshots.setdefault('low_capacity_records', {})[path.name] = digest(path)

    if include_history:
        return snapshots, refs, dict(low_capacity=low_records, prior_local=local_records)
    return snapshots, refs, {}


def prepare_inputs(env, out):
    inputs = env.get('inputs', {})
    refs = {}
    source_env = None if env['fixture'] else read(Path(env['source_results']) / 'environment.json')
    for case in cases(env['preset']):
        cid = case['case_id']
        spec = plan(env['preset'])['local_lr']
        if cid in inputs:
            item = inputs[cid]
            prepared = Path(item['path'])
            if digest(prepared / 'prepared.json') != item['metadata_sha256']:
                raise ValueError('Prepared cache changed: ' + cid)
        elif env['fixture']:
            print('Preparing independent synthetic cache: ' + cid, flush=True)
            prepared = quantity_data.prepare(env['cache'], DIR / 'fixture_data', spec,
                case['seed'], case['partition'], profile='strong', fixture=True)
            item = dict(path=str(prepared.resolve()), metadata_sha256=digest(prepared / 'prepared.json'))
        else:
            item = dict(source_env['inputs'][input_key(case)])
            prepared = Path(item['path'])
        quantity_data.verify(prepared, spec.config, case['seed'], case['partition'],
                             profile='strong', fixture=env['fixture'])
        probe = probe_manifest(case['seed'], np.load(prepared / 'public_ids.npy', allow_pickle=False)[:spec.config.samples],
                               PROBE_SIZES[env['preset']])
        if item.get('probe_manifest', probe) != probe:
            raise ValueError('Probe identity changed: ' + cid)
        item['probe_manifest'] = probe
        if env['fixture']:
            reference_path = Path(item['reference_path']) if item.get('reference_path') else out / 'references' / (cid + '.json')
            if not reference_path.exists():
                with threadpool_limits(limits=1):
                    reference = quantity_engine.run(prepared, spec, 'B', profile='strong', fixture=True, progress=False)
                write_new(reference_path, seal(reference))
        else:
            old_case = next(m for m in quantity_run.schedule('full')
                            if m['seed'] == case['seed'] and m['partition'] == case['partition']
                            and m['profile'] == 'strong' and m['method'] == 'B')
            reference_path = Path(env['source_results']) / 'runs' / quantity_run.filename(old_case)
        if item.get('reference_sha256', digest(reference_path)) != digest(reference_path):
            raise ValueError('Reference result changed: ' + cid)
        reference = read(reference_path)
        if reference.get('run_sha256') != seal(dict(reference))['run_sha256']:
            raise ValueError('Reference run seal mismatch: ' + cid)
        if not env['fixture']:
            old_meta = next(m for m in quantity_run.schedule('full')
                            if m['seed'] == case['seed'] and m['partition'] == case['partition']
                            and m['profile'] == 'strong' and m['method'] == 'B')
            quantity_run.verify_record(reference, old_meta, quantity_run.plan('full')['strong'],
                                        prepared, False, False)
        item.update(reference_path=str(reference_path.resolve()), reference_sha256=digest(reference_path))
        inputs[cid] = item
        refs[cid] = reference
        env['inputs'] = inputs
        write_new(out / 'environment.json', env)
        print('Verified cache, graph and probe identity: ' + cid, flush=True)
    return refs


def verify_record(record, meta, spec, entry, fixture):
    local_run.verify_record(record, meta, spec, entry, fixture)
    expected_weights = client_weights('local_lr')
    if record.get('public_client_weights') != expected_weights:
        raise ValueError('Per-client LR vector differs')
    if record['config']['public_weight'] != .5 or record['config']['head_lr'] != .1:
        raise ValueError('Main spec must retain the registered private/public weights')
    if record['config']['rounds'] != spec.config.rounds:
        raise ValueError('Round count differs')
    for diagnostic in [record['initial_diagnostics'], *record['diagnostic_records']]:
        weights = [c['actual_public_weight'] for c in diagnostic['clients']]
        rates = [c['actual_public_effective_lr'] for c in diagnostic['clients']]
        if weights != expected_weights or rates != [.0125, .05, .05, .0125, .05, .05]:
            raise ValueError('Actual per-client public LR differs')
    return True


def worker(env, out, index):
    check_environment(env)
    meta = env['schedule'][index]
    spec = plan(env['preset'])[meta['branch']]
    entry = env['inputs'][meta['case_id']]
    prepared = Path(entry['path'])
    if digest(prepared / 'prepared.json') != entry['metadata_sha256']:
        raise ValueError('Prepared metadata changed')
    if digest(entry['reference_path']) != entry['reference_sha256']:
        raise ValueError('Quantity reference changed')
    power = power_status()
    if not env['fixture'] and power['ac_line_status'] != 1:
        print('AC power not detected; continuing quality-only confirmation (power state logged).', flush=True)
    started, tick = time.time(), time.perf_counter()
    with threadpool_limits(limits=1):
        record = engine_run(prepared, spec, branch='local_lr', fixture=env['fixture'])
    record.update(worker_started_utc=started, worker_ended_utc=time.time(),
                  engine_wall_seconds=time.perf_counter() - tick,
                  worker_started_power=power, worker_ended_power=power_status())
    record = seal(record)
    verify_record(record, meta, spec, entry, env['fixture'])
    reference = read(entry['reference_path'])
    if record['initial_head_digest'] != reference['initial_head_digest'] or record['graph_sha256'] != reference['graph_sha256']:
        raise ValueError('Confirmation changed initial head or graph')
    if record['probe_manifest'] != entry['probe_manifest']:
        raise ValueError('Confirmation probe selection changed')
    write_new(out / 'runs' / filename(meta), record)


def _verify_finished(out):
    completed = read(out / 'completed.json')
    for name, expected in completed['files'].items():
        if digest(out / name) != expected:
            raise ValueError('Completed artifact changed: ' + name)
    if read(out / 'finished.json').get('completed_manifest_sha256') != digest(out / 'completed.json'):
        raise ValueError('Completion seal mismatch')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset', choices=('full', 'smoke'), default='full')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--source-results', type=Path, default=ROOT / 'experiments/quantity_heterogeneity/results_full')
    ap.add_argument('--local-history-results', type=Path, default=ROOT / 'experiments/local_public_lr/results_full')
    ap.add_argument('--diagnostic-results', type=Path, default=ROOT / 'experiments/low_capacity_diagnostic/results_full')
    ap.add_argument('--cache', type=Path, default=DIR / 'prepared')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    args = ap.parse_args()
    out = (args.output or DIR / f'results_{args.preset}').resolve()
    if args.worker is not None:
        worker(read(out / 'environment.json'), out, args.worker)
        return
    if args.resume:
        env = read(out / 'environment.json')
        check_environment(env)
        if (out / 'completed.json').exists():
            _verify_finished(out)
            print('Already complete; verified sealed manifest: ' + str(out / 'report.md'))
            return
        args.cache = Path(env['cache'])
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Use --resume or select a new output directory')
        preset = args.preset
        env = dict(preset=preset, fixture=preset == 'smoke',
                   plan={b: s.json() for b, s in plan(preset).items()},
                   schedule=schedule(preset), sources=sources(), runtime=runtime(),
                   source_results=str(args.source_results.resolve()),
                   local_history_results=str(args.local_history_results.resolve()),
                   diagnostic_results=str(args.diagnostic_results.resolve()),
                   cache=str(args.cache.resolve()), plan_commit=PLAN_COMMIT,
                   public_client_weights={'local_lr': client_weights()},
                   probe_config=dict(stream=PROBE_STREAM, size=PROBE_SIZES[preset],
                                     selection='sorted local choice without replacement'),
                   started_utc=time.time())
    power = power_status()
    if not env['fixture'] and power['ac_line_status'] != 1:
        print('AC power not detected; continuing quality-only confirmation (power state logged).', flush=True)
    out.mkdir(parents=True, exist_ok=True)
    write_new(out / 'environment.json', env)
    write_new(out / f'invocation_{time.time_ns()}.json', dict(resume=args.resume, utc=time.time(), power=power))

    with Monitor(out / f"power_{time.time_ns()}.jsonl", interval=15):
        if not env['fixture']:
            snapshots, references, history = _history_snapshot(env, include_history=True)
            if env.get('historical_sources') not in (None, snapshots):
                raise ValueError('Historical result manifests changed')
            env['historical_sources'] = snapshots
            env['historical_record_roles'] = {
                'quantity_B': 'full-length reference per matching case',
                'low_capacity_baseline': 'recorded 40-round reference only',
                'low_capacity_low_lr_private_only': 'historical diagnostic context',
                'prior_single_case_local_lr': 'exploratory history only'}
            write_new(out / 'environment.json', env)
        else:
            references, history = {}, {}
        references.update(prepare_inputs(env, out))
        completed = []
        for index, meta in enumerate(env['schedule']):
            target = out / 'runs' / filename(meta)
            if not target.exists():
                print('Running: ' + target.name, flush=True)
                subprocess.run([sys.executable, '-m', 'experiments.local_public_lr_confirmation.run',
                                '--output', str(out), '--worker', str(index)], cwd=ROOT, check=True)
            else:
                print('Preserved: ' + target.name, flush=True)
            record = read(target)
            entry = env['inputs'][meta['case_id']]
            verify_record(record, meta, plan(env['preset'])[meta['branch']], entry, env['fixture'])
            reference = references[meta['case_id']]
            if record['initial_head_digest'] != reference['initial_head_digest'] or record['graph_sha256'] != reference['graph_sha256']:
                raise ValueError('Initial head/graph no longer match source case')
            completed.append((meta, record))
        if {p.name for p in (out / 'runs').glob('*.json')} != {filename(m) for m in env['schedule']}:
            raise ValueError('Unexpected or missing run files')
        if not env['fixture']:
            # Re-open and re-hash all frozen source manifests after execution.
            final_snapshots, _, _ = _history_snapshot(env, include_history=False)
            if final_snapshots != env['historical_sources']:
                raise ValueError('Historical source changed during this run')
        reports(out, completed, references, fixture=env['fixture'], history=history)
        check_environment(env)

    ended = power_status()
    write_new(out / 'environment_final.json', dict(**env, ended_utc=time.time(), ended_power=ended))
    files = {str(p.relative_to(out)): digest(p) for p in sorted(out.rglob('*'))
             if p.is_file() and p.name not in ('completed.json', 'finished.json')}
    write_new(out / 'completed.json', dict(runs=len(completed), expected_runs=len(env['schedule']),
        record_validation_passed=True, certification_comparisons_performed=False,
        relation_mismatches=None, files=files))
    write_new(out / 'finished.json', dict(status='complete', completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
