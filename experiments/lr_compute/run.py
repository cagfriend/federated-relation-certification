"""P1 independent-process resource comparison, using frozen LR-confirmation inputs."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

from threadpoolctl import threadpool_limits
from experiments.public_lr_confirmation import run as confirmation
from experiments.public_lr_confirmation import data as input_data
from experiments.k_scaling import data as k_data
from experiments.k_scaling.engine import run as engine_run
from experiments.client_scaling.run import verify_record as core_verify, non_time_rows
from experiments.client_scaling.telemetry import Monitor
from experiments.public_scaling.data import runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.stl10_transfer.run import digest, seal, write_new, power_status
from experiments.stl10_compute.run import TRAJECTORY_KEYS
from .design import plan, schedule, filename, METHODS
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
SLEEP_RECORD = ROOT / 'outputs/k_scaling_sleep_review_20261102/EXCLUSION.json'
read = confirmation.read


def sources():
    values = confirmation.sources()
    for p in DIR.glob('*.py'):
        values[str(p.relative_to(ROOT))] = digest(p)
    values['experiments/lr_compute/PREREGISTRATION.md'] = digest(DIR / 'PREREGISTRATION.md')
    values[str(SLEEP_RECORD.relative_to(ROOT))] = digest(SLEEP_RECORD)
    return values


def check_environment(env):
    if env['sources'] != sources():
        raise ValueError('Frozen sources changed')
    current = runtime()
    for key in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform'):
        if current.get(key) != env['runtime'].get(key):
            raise ValueError('Runtime changed: ' + key)
    if env['plan'] != {k: s.json() for k, s in plan(env['preset']).items()}:
        raise ValueError('Frozen plan changed')


def input_for(env, case_id):
    item = env['inputs'][case_id]
    if digest(item['source_marker']) != item['source_marker_sha256']:
        raise ValueError('Source input marker changed')
    if read(item['source_marker']) != item['entry']:
        raise ValueError('Input identity differs')
    if digest(item['anchor']) != item['anchor_sha256']:
        raise ValueError('Diagnostic anchor changed')
    return item


def preparation(entry, spec):
    base = read(Path(entry['base_directory']) / 'prepared.json')
    extra = 0.0
    contaminated = False
    reason = ''
    if spec.config.classes == 64:
        meta = read(Path(entry['k_directory']) / 'prepared_k.json')
        extra = meta['additional_preparation_seconds']
        old = read(SLEEP_RECORD)['contaminated_preparation_case']
        contaminated = (entry['seed'] == old['seed'] and entry['partition'] == old['partition']
                        and extra == old['whole_additional_preparation_seconds'])
        if contaminated:
            reason = 'Historical K64 preparation sleep contamination; original EXCLUSION.json retained'
    return dict(base_seconds=base['preparation_wall_seconds_excluding_download'],
                additional_seconds_raw=extra, additional_seconds=None if contaminated else extra,
                known_contamination=contaminated, reason=reason)


def validate(record, meta, spec, entry, memory, fixture):
    if record.get('study_case') != meta['case_id'] or record.get('family') != meta['family'] or record.get('role') != meta['role']:
        raise ValueError('Study case differs')
    expected_meta = dict(seed=meta['seed'], partition=meta['partition'], method=meta['method'],
                         regime='fixed_total', clients=len(spec.config.dimensions))
    core_verify(record, expected_meta, spec, entry['base_directory'], memory, fixture)
    if record['preparation'] != preparation(entry, spec):
        raise ValueError('Preparation accounting differs')
    expected = record['preparation']
    summary = record['summary'][meta['method']]
    total = None if expected['known_contamination'] else (expected['base_seconds'] + expected['additional_seconds']
               + record['shared_loading_seconds'] + summary['head_pipeline_seconds'])
    if summary['with_shared_preparation_seconds'] != total:
        raise ValueError('Preparation total differs')


def compare_anchor(record, anchor):
    if record['initial_head_digest'] != anchor['initial_head_digest'] or record['graph_sha256'] != anchor['graph_sha256']:
        raise ValueError('Anchor starting state differs')
    if len(record['round_records']) != len(anchor['round_records']):
        raise ValueError('Anchor rounds differ')
    for row, old in zip(record['round_records'], anchor['round_records']):
        if any(row[k] != old[k] for k in TRAJECTORY_KEYS if k not in ('traffic',)):
            raise ValueError('Training differs from LR0.05 anchor')
        if row['traffic'] != old['traffic']:
            raise ValueError('Traffic differs from anchor')
    old_metrics = {x['round']: x for x in anchor['metrics']}
    if record['round_records'][-1]['round'] >= 20:
        expected = set(range(20, record['round_records'][-1]['round'] + 1, 20))
        if not expected.issubset(old_metrics):
            raise ValueError('Missing common anchor checkpoints')
    for metric in record['metrics']:
        if metric['round'] not in old_metrics:
            continue
        old = old_metrics[metric['round']]
        if metric['clients'] != old['clients'] or metric['mean'] != old['mean']:
            raise ValueError('Anchor evaluation differs')


def groups_check(completed):
    groups = {}
    for meta, record in completed:
        group = groups.setdefault(meta['case_id'], {})
        if meta['method'] in group:
            raise ValueError('Duplicate method')
        group[meta['method']] = record
    for cid, group in groups.items():
        if set(group) != set(METHODS):
            raise ValueError('Incomplete triple: ' + cid)
        baseline = group['B']
        for method in ('E', 'D'):
            compare_anchor(group[method], baseline)
            if group[method]['summary'][method]['initial_traffic'] != baseline['summary']['B']['initial_traffic']:
                raise ValueError('Initial traffic differs')
            if group[method]['summary'][method]['traffic'] != baseline['summary']['B']['traffic']:
                raise ValueError('Total traffic differs')
    return groups


def worker(env, out, job, memory):
    check_environment(env)
    meta = schedule(env['preset'], memory)[job]
    spec = plan(env['preset'])[meta['case_id']]
    item = input_for(env, meta['case_id'])
    entry = item['entry']
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required')
    input_data.verify_input(entry, spec, fixture=env['fixture'])
    paths = (k_data.pseudo_paths(entry['k_directory']) if spec.config.classes == 64 else
             [Path(entry['base_directory']) / f'client_{i}_pseudo.npy' for i in range(len(spec.config.dimensions))])
    started = time.time()
    with threadpool_limits(limits=1):
        record = engine_run(entry['base_directory'], spec, paths, method=meta['method'], fixture=env['fixture'],
                            validate=not memory, metrics=not memory, progress=True)
    record.update(study_case=meta['case_id'], family=meta['family'], role=meta['role'],
                  partition=meta['partition'], method=meta['method'], regime='fixed_total',
                  clients=len(spec.config.dimensions), memory_mode=memory,
                  process_peak_bytes=native_peak_bytes(), worker_started_utc=started, worker_ended_utc=time.time())
    record['preparation'] = preparation(entry, spec)
    prep = record['preparation']
    record['summary'][meta['method']]['with_shared_preparation_seconds'] = (None if prep['known_contamination'] else
        prep['base_seconds'] + prep['additional_seconds'] + record['shared_loading_seconds'] + record['summary'][meta['method']]['head_pipeline_seconds'])
    record = seal(record)
    validate(record, meta, spec, entry, memory, env['fixture'])
    if not memory:
        anchor_item = read(item['anchor'])
        confirmation.check_seal(anchor_item)
        compare_anchor(record, anchor_item['result'])
    write_new(out / ('memory' if memory else 'runs') / filename(meta), record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--source-results', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', type=int)
    parser.add_argument('--memory-worker', action='store_true')
    args = parser.parse_args()
    out = (args.output or DIR / f'results_{args.preset}').resolve()
    if args.worker is not None:
        worker(read(out / 'environment.json'), out, args.worker, args.memory_worker)
        return
    if args.resume:
        env = read(out / 'environment.json')
        check_environment(env)
        if (out / 'completed.json').exists():
            for name, sha in read(out / 'completed.json')['files'].items():
                if digest(out / name) != sha:
                    raise ValueError('Completed result changed: ' + name)
            print('Already complete: ' + str(out / 'report.md'))
            return
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Use --resume or a new output')
        source = (args.source_results or ROOT / 'experiments/public_lr_confirmation' / f'results_{args.preset}').resolve()
        source_env = read(source / 'environment.json')
        confirmation.environment_check(source_env)
        if source_env['preset'] != args.preset:
            raise ValueError('Source preset differs')
        for name, sha in read(source / 'completed.json')['files'].items():
            if digest(source / name) != sha:
                raise ValueError('Source result changed: ' + name)
        inputs = {}
        for cid, spec in plan(args.preset).items():
            marker = source / 'inputs' / f'{cid}.json'
            anchor = source / 'records' / f'{cid}_public2_half.json'
            entry = read(marker)
            case = next(c for c in source_env['cases'] if c['case_id'] == cid)
            if any(entry[k] != case[k] for k in ('seed', 'partition', 'family')):
                raise ValueError('Input case mismatch')
            anchor_item = read(anchor)
            confirmation.envelope_check(anchor_item, case, 'public2_half',
                                        confirmation.spec_for(args.preset, case['family'], source_env['device']), source)
            inputs[cid] = dict(entry=entry, source_marker=str(marker), source_marker_sha256=digest(marker),
                               anchor=str(anchor), anchor_sha256=digest(anchor))
        env = dict(preset=args.preset, fixture=args.preset == 'smoke', sources=sources(), runtime=runtime(),
                   plan={k:s.json() for k,s in plan(args.preset).items()}, inputs=inputs, started_utc=time.time())
        if not env['fixture'] and power_status()['ac_line_status'] != 1:
            raise RuntimeError('AC power required')
        out.mkdir(parents=True, exist_ok=True)
        write_new(out / 'environment.json', env)
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required on resume')
    completed, memories = [], []
    with Monitor(out / f'power_{time.time_ns()}.jsonl'):
        for memory in (False, True):
            jobs = schedule(env['preset'], memory)
            for job, meta in enumerate(jobs):
                spec = plan(env['preset'])[meta['case_id']]
                item = input_for(env, meta['case_id'])
                path = out / ('memory' if memory else 'runs') / filename(meta)
                if not path.exists():
                    print(('Memory: ' if memory else 'Running: ') + path.name, flush=True)
                    command = [sys.executable, '-m', 'experiments.lr_compute.run', '--output', str(out), '--worker', str(job)]
                    if memory:
                        command.append('--memory-worker')
                    subprocess.run(command, cwd=ROOT, check=True)
                else:
                    print('Preserved: ' + path.name, flush=True)
                record = read(path)
                validate(record, meta, spec, item['entry'], memory, env['fixture'])
                if memory:
                    reference = next(r for m,r in completed if m['case_id']==meta['case_id'] and m['method']==meta['method'])
                    if non_time_rows(record) != non_time_rows(reference) or record['initial_head_digest'] != reference['initial_head_digest']:
                        raise ValueError('Memory replay differs')
                    memories.append((meta, record))
                else:
                    compare_anchor(record, read(item['anchor'])['result'])
                    completed.append((meta, record))
                    if (job + 1) % 3 == 0:
                        groups_check(completed[-3:])
            if {p.name for p in (out/('memory' if memory else 'runs')).glob('*.json')} != {filename(m) for m in jobs}:
                raise ValueError('Unexpected result files')
        groups_check(completed)
        reports(out, completed, memories, fixture=env['fixture'])
    check_environment(env)
    write_new(out / 'environment_final.json', dict(**env, ended_utc=time.time(), ended_power=power_status()))
    write_new(out / 'completed.json', dict(runs=len(completed), memory_runs=len(memories), mismatches=0,
              files={str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json','finished.json')}))
    write_new(out / 'finished.json', dict(completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
