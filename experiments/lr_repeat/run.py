"""P2 three paired, order-balanced technical repetitions for four fixed cases."""
import argparse
from pathlib import Path
import subprocess
import sys
import time

from threadpoolctl import threadpool_limits
from experiments.lr_compute import run as p1
from experiments.lr_compute.design import filename as p1_filename
from experiments.k_scaling.engine import run as engine_run
from experiments.k_scaling import data as k_data
from experiments.public_lr_confirmation import data as input_data
from experiments.client_scaling.telemetry import Monitor
from experiments.public_scaling.data import runtime
from experiments.public_scaling.util import native_peak_bytes
from experiments.stl10_transfer.run import digest, seal, write_new, power_status
from .design import plan, schedule, filename, METHODS, REPEATS
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
read = p1.read


def sources():
    values = p1.sources()
    for path in DIR.glob('*.py'):
        values[str(path.relative_to(ROOT))] = digest(path)
    values['experiments/lr_repeat/PREREGISTRATION.md'] = digest(DIR / 'PREREGISTRATION.md')
    return values


def check_environment(env):
    if env['sources'] != sources():
        raise ValueError('Frozen sources changed')
    now = runtime()
    for key in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform'):
        if now.get(key) != env['runtime'].get(key):
            raise ValueError('Runtime changed: ' + key)
    if env['plan'] != {cid:s.json() for cid,s in plan(env['preset']).items()}:
        raise ValueError('Frozen plan differs')
    if env['schedule'] != schedule(env['preset']):
        raise ValueError('Frozen order differs')


def anchor_for(env, meta):
    item = env['anchors'][f"{meta['case_id']}|{meta['method']}"]
    if digest(item['path']) != item['sha256']:
        raise ValueError('P1 method anchor changed')
    anchor = read(item['path'])
    entry = p1.input_for(env, meta['case_id'])['entry']
    spec = plan(env['preset'])[meta['case_id']]
    p1.validate(anchor, meta, spec, entry, False, env['fixture'])
    return anchor


def validate(record, meta, spec, entry, fixture):
    if type(record.get('repeat')) is not int or record['repeat'] != meta['repeat']:
        raise ValueError('Repeat identity differs')
    if record.get('position') != meta['position']:
        raise ValueError('Method position differs')
    p1.validate(record, meta, spec, entry, False, fixture)


def compare_method(record, anchor):
    p1.compare_anchor(record, anchor)
    if p1.non_time_rows(record) != p1.non_time_rows(anchor):
        raise ValueError('Method-specific counters differ')
    for key in ('persistent_method_array_bytes', 'initial_traffic', 'traffic',
                'public_optimizer_steps', 'private_optimizer_steps',
                'private_forward_endpoints', 'student_forward_endpoints'):
        method = record['method']
        if record['summary'][method][key] != anchor['summary'][method][key]:
            raise ValueError('Non-timing summary differs: ' + key)


def verify_blocks(completed):
    cases = {}
    for meta, record in completed:
        cases.setdefault(meta['case_id'], []).append((meta, record))
    for cid, items in cases.items():
        if len(items) != REPEATS * len(METHODS):
            raise ValueError('Incomplete repeat block: ' + cid)
        for repeat in range(REPEATS):
            triple = [(m,r) for m,r in items if m['repeat'] == repeat]
            if len(triple) != 3 or {m['method'] for m,r in triple} != set(METHODS):
                raise ValueError('Repeat composition differs')
            p1.groups_check(triple)
        for method in METHODS:
            rows = [r for m,r in items if m['method'] == method]
            if len(rows) != REPEATS:
                raise ValueError('Method repetition count differs')
            for row in rows[1:]:
                compare_method(row, rows[0])
    return cases


def worker(env, out, index):
    check_environment(env)
    meta = env['schedule'][index]
    spec = plan(env['preset'])[meta['case_id']]
    entry = p1.input_for(env, meta['case_id'])['entry']
    anchor = anchor_for(env, meta)
    start_power = power_status()
    if not env['fixture'] and start_power['ac_line_status'] != 1:
        raise RuntimeError('AC power required')
    input_data.verify_input(entry, spec, fixture=env['fixture'])
    paths = (k_data.pseudo_paths(entry['k_directory']) if spec.config.classes == 64 else
             [Path(entry['base_directory']) / f'client_{i}_pseudo.npy' for i in range(len(spec.config.dimensions))])
    started = time.time()
    engine_started = time.perf_counter()
    with threadpool_limits(limits=1):
        record = engine_run(entry['base_directory'], spec, paths, method=meta['method'],
                            fixture=env['fixture'], validate=True, metrics=True, progress=True)
    record.update(study_case=meta['case_id'], family=meta['family'], role=meta['role'],
                  partition=meta['partition'], method=meta['method'], regime='fixed_total',
                  clients=len(spec.config.dimensions), memory_mode=False, repeat=meta['repeat'], position=meta['position'],
                  process_peak_bytes=native_peak_bytes(), worker_started_utc=started, worker_ended_utc=time.time(),
                  engine_wall_seconds=time.perf_counter() - engine_started,
                  worker_started_power=start_power, worker_ended_power=power_status())
    prep = p1.preparation(entry, spec)
    record['preparation'] = prep
    summary = record['summary'][meta['method']]
    summary['with_shared_preparation_seconds'] = (None if prep['known_contamination'] else
        prep['base_seconds'] + prep['additional_seconds'] + record['shared_loading_seconds'] + summary['head_pipeline_seconds'])
    record = seal(record)
    validate(record, meta, spec, entry, env['fixture'])
    compare_method(record, anchor)
    write_new(out / 'runs' / filename(meta), record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--source-results', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', type=int)
    args = parser.parse_args()
    out = (args.output or DIR / f'results_{args.preset}').resolve()
    if args.worker is not None:
        worker(read(out / 'environment.json'), out, args.worker)
        return
    if args.resume:
        env = read(out / 'environment.json')
        check_environment(env)
        if (out / 'completed.json').exists():
            for name, value in read(out / 'completed.json')['files'].items():
                if digest(out / name) != value:
                    raise ValueError('Completed result changed: ' + name)
            print('Already complete: ' + str(out / 'report.md'))
            return
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Use --resume or a new output')
        print('Checking completed P1 inputs and method anchors...', flush=True)
        source = (args.source_results or ROOT / 'experiments/lr_compute' / f'results_{args.preset}').resolve()
        source_env = read(source / 'environment.json')
        p1.check_environment(source_env)
        if source_env['preset'] != args.preset:
            raise ValueError('Source preset differs')
        for name, value in read(source / 'completed.json')['files'].items():
            if digest(source / name) != value:
                raise ValueError('P1 completed result changed: ' + name)
        anchors = {}
        inputs = {}
        for meta in schedule(args.preset):
            cid = meta['case_id']
            inputs[cid] = p1.input_for(source_env, cid)
            path = source / 'runs' / p1_filename(meta)
            anchors[f"{cid}|{meta['method']}"] = dict(path=str(path), sha256=digest(path))
        env = dict(preset=args.preset, fixture=args.preset == 'smoke', sources=sources(), runtime=runtime(),
                   plan={cid:s.json() for cid,s in plan(args.preset).items()}, schedule=schedule(args.preset),
                   inputs=inputs, anchors=anchors, source_results=str(source), started_utc=time.time())
        if not env['fixture'] and power_status()['ac_line_status'] != 1:
            raise RuntimeError('AC power required')
        # Validate every method anchor before any new method is launched.
        checked = set()
        for meta in env['schedule']:
            key = meta['case_id'], meta['method']
            if key not in checked:
                anchor_for(env, meta)
                checked.add(key)
        out.mkdir(parents=True, exist_ok=True)
        write_new(out / 'environment.json', env)
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required on resume')
    completed = []
    with Monitor(out / f'power_{time.time_ns()}.jsonl'):
        for index, meta in enumerate(env['schedule']):
            path = out / 'runs' / filename(meta)
            if not path.exists():
                print('Running: ' + path.name, flush=True)
                subprocess.run([sys.executable, '-m', 'experiments.lr_repeat.run', '--output', str(out),
                                '--worker', str(index)], cwd=ROOT, check=True)
            else:
                print('Preserved: ' + path.name, flush=True)
            record = read(path)
            spec = plan(env['preset'])[meta['case_id']]
            validate(record, meta, spec, p1.input_for(env, meta['case_id'])['entry'], env['fixture'])
            compare_method(record, anchor_for(env, meta))
            completed.append((meta, record))
            if (index + 1) % 3 == 0:
                p1.groups_check(completed[-3:])
            if (index + 1) % 9 == 0:
                verify_blocks(completed[-9:])
        if {p.name for p in (out / 'runs').glob('*.json')} != {filename(m) for m in env['schedule']}:
            raise ValueError('Unexpected results')
        verify_blocks(completed)
        reports(out, completed, fixture=env['fixture'])
    check_environment(env)
    write_new(out / 'environment_final.json', dict(**env, ended_utc=time.time(), ended_power=power_status()))
    write_new(out / 'completed.json', dict(runs=len(completed), blocks=len(plan(env['preset'])), mismatches=0,
              files={str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json','finished.json')}))
    write_new(out / 'finished.json', dict(completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
