"""B-only learning-rate confirmation with explicit historical provenance."""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import time

from threadpoolctl import threadpool_limits
from experiments.collapse_intervention.engine import drive
from experiments.collapse_intervention import run as diagnostic
from experiments.collapse_intervention.run import read, branch_spec, validate, check_reference
from experiments.stl10_transfer.run import digest, seal, write_new, power_status
from experiments.public_scaling.data import runtime
from . import data
from .design import cases, spec_for
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DIR = Path(__file__).parent
ARMS = ('reference2', 'public2_half')


def sources():
    values = diagnostic.sources()
    for path in DIR.glob('*.py'):
        values[str(path.relative_to(ROOT))] = digest(path)
    values['experiments/public_lr_confirmation/PREREGISTRATION.md'] = digest(DIR / 'PREREGISTRATION.md')
    return values


def environment_check(env):
    if env['sources'] != sources():
        raise ValueError('Frozen sources changed')
    now = runtime()
    for key in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch', 'platform'):
        if now.get(key) != env['runtime'].get(key):
            raise ValueError('Runtime changed: ' + key)
    if env['cases'] != cases(env['preset']):
        raise ValueError('Matrix changed')


def check_seal(record):
    if record.get('run_sha256') != seal(dict(record))['run_sha256']:
        raise ValueError('Record seal differs')


def history_path(case, arm, fixture):
    if fixture or case['role'] == 'new_seed':
        return None
    family, seed, part = case['family'], case['seed'], case['partition']
    if arm == 'public2_half':
        return ROOT / 'experiments/collapse_intervention/results_full/runs/public2_half.json' if family == 'n12_k10' and seed == 1003 else None
    if family == 'n12_k10':
        return ROOT / f'experiments/client_scaling/results_full_fixed_total/runs/fixed_total_N12_{part}_seed_{seed}_B.json'
    return ROOT / f'experiments/k_scaling/results_full/runs/{part}_k64_seed{seed}_B.json'


def load_history(path, case, spec, entry, arm):
    source_environment = read(path.parent.parent / 'environment.json')
    for name, value in source_environment['sources'].items():
        if digest(ROOT / name) != value:
            raise ValueError('Historical execution source changed: ' + name)
    raw = read(path)
    check_seal(raw)
    if raw['seed'] != case['seed'] or raw['partition'] != case['partition']:
        raise ValueError('Historical case differs')
    if raw['spec'] != branch_spec(spec, arm).json():
        raise ValueError('Historical configuration differs')
    if Path(raw['prepared_directory']).resolve() != Path(entry['base_directory']).resolve():
        raise ValueError('Historical feature cache differs')
    if case['family'] == 'n6_k64' and Path(raw['pseudo_directory']).resolve() != Path(entry['k_directory']).resolve():
        raise ValueError('Historical K64 targets differ')
    if arm == 'public2_half':
        if raw['arm'] != arm:
            raise ValueError('Historical intervention differs')
        return raw
    expected_members = 0  # B has no candidate-set oracle.
    validation = raw['validation']
    if (not validation['enabled'] or validation['mismatches'] != 0
            or validation['relation_comparisons'] != spec.config.rounds * len(spec.config.dimensions) * spec.config.samples // 2
            or validation['candidate_membership_comparisons'] != expected_members):
        raise ValueError('Historical B oracle coverage differs')
    return dict(arm=arm, seed=case['seed'], partition=case['partition'], spec=raw['spec'],
                initial_head_digest=raw['initial_head_digest'], graph_sha256=raw['graph_sha256'],
                final_head_digest=raw['summary']['B']['final_head_digest'], round_records=raw['round_records'],
                metrics=raw['metrics'], stages=[], rounds=spec.config.rounds)


def envelope_check(item, case, arm, spec, out):
    check_seal(item)
    if item['case'] != case or item['arm'] != arm:
        raise ValueError('Stored run identity differs')
    result = item['result']
    if result['arm'] != arm or result['seed'] != case['seed'] or result['partition'] != case['partition']:
        raise ValueError('Training identity differs')
    if result['spec'] != branch_spec(spec, arm).json():
        raise ValueError('Training configuration differs')
    if [r['round'] for r in result['round_records']] != list(range(1, spec.config.rounds + 1)):
        raise ValueError('Incomplete training')
    if item['origin'] == 'historical':
        if digest(item['source_path']) != item['source_sha256']:
            raise ValueError('Historical source changed')
    else:
        check_seal(result)
    if result['final_head_digest'] != result['round_records'][-1]['head_digest_after_public']:
        raise ValueError('Final head differs')


def check_pair(case, spec, records):
    b = records[case['case_id'], 'reference2']['result']
    d = records[case['case_id'], 'public2_half']['result']
    # Candidate records have the complete diagnostic schema in both origins.
    validate(d, spec, b, expected_arm='public2_half')
    if d['graph_sha256'] != b['graph_sha256']:
        raise ValueError('Paired graph differs')
    for x, y in zip(d['round_records'], b['round_records']):
        if x['public_schedule_digest'] != y['public_schedule_digest']:
            raise ValueError('Public edge order differs')
    if d['round_records'][0]['committed_counts_digest'] != b['round_records'][0]['committed_counts_digest']:
        raise ValueError('First teacher target differs')


def worker(env, out, index, arm):
    environment_check(env)
    case = env['cases'][index]
    spec = spec_for(env['preset'], case['family'], env['device'])
    entry = read(out / 'inputs' / f"{case['case_id']}.json")
    if any(entry.get(k) != case[k] for k in ('family', 'seed', 'partition')):
        raise ValueError('Input case differs')
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required')
    with threadpool_limits(limits=1):
        prepared = data.load_input(entry, spec, fixture=env['fixture'])
        try:
            result = drive(prepared, spec, arm, progress=True)
        finally:
            prepared.close()
    result.update(seed=case['seed'], partition=case['partition'])
    result = seal(result)
    item = seal(dict(case=case, arm=arm, origin='new', result=result, completed_utc=time.time()))
    envelope_check(item, case, arm, spec, out)
    if arm == 'public2_half':
        baseline = read(out / 'records' / f"{case['case_id']}_reference2.json")['result']
        validate(result, spec, baseline, expected_arm=arm)
    else:
        validate(result, spec, result, expected_arm=arm)
    write_new(out / 'records' / f"{case['case_id']}_{arm}.json", item)


def execute(env, out):
    records = {}
    for index, case in enumerate(env['cases']):
        spec = spec_for(env['preset'], case['family'], env['device'])
        marker = out / 'inputs' / f"{case['case_id']}.json"
        if marker.exists():
            entry = read(marker)
            if any(entry.get(k) != case[k] for k in ('family', 'seed', 'partition')):
                raise ValueError('Input case differs')
            data.verify_input(entry, spec, fixture=env['fixture'])
        else:
            print('Preparing: ' + case['case_id'], flush=True)
            entry = data.prepare_input(DIR, case, spec, fixture=env['fixture'])
            write_new(marker, entry)
        preflight_path = out / 'preflight' / f"{case['case_id']}.json"
        if preflight_path.exists():
            preflight = read(preflight_path)
            check_seal(preflight)
        else:
            prefix = replace(spec, config=replace(spec.config, rounds=3))
            with threadpool_limits(limits=1):
                prepared = data.load_input(entry, prefix, fixture=env['fixture'])
                try:
                    preflight = seal(drive(prepared, prefix, 'reference2', observations=False))
                finally:
                    prepared.close()
            write_new(preflight_path, preflight)
        for arm in ARMS:
            path = out / 'records' / f"{case['case_id']}_{arm}.json"
            if not path.exists():
                history = history_path(case, arm, env['fixture'])
                if history is not None:
                    print('Historical: ' + path.name, flush=True)
                    result = load_history(history, case, spec, entry, arm)
                    write_new(path, seal(dict(case=case, arm=arm, origin='historical', result=result,
                                             source_path=str(history), source_sha256=digest(history))))
                else:
                    print('Running: ' + path.name, flush=True)
                    subprocess.run([sys.executable, '-m', 'experiments.public_lr_confirmation.run',
                                    '--output', str(out), '--worker', str(index), '--arm', arm], cwd=ROOT, check=True)
            item = read(path)
            envelope_check(item, case, arm, spec, out)
            records[case['case_id'], arm] = item
            if arm == 'reference2':
                check_reference(preflight, item['result'])
        check_pair(case, spec, records)
    expected = {f"{c['case_id']}_{arm}.json" for c in env['cases'] for arm in ARMS}
    if {p.name for p in (out / 'records').glob('*.json')} != expected:
        raise ValueError('Unexpected records')
    reports(out, env['cases'], records)
    return sum(v['origin'] == 'new' for v in records.values())


def main():
    from experiments.client_scaling.telemetry import Monitor
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepare-device', choices=('cpu', 'cuda'))
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', type=int)
    parser.add_argument('--arm', choices=ARMS)
    args = parser.parse_args()
    out = (args.output or DIR / f'results_{args.preset}').resolve()
    if args.worker is not None:
        worker(read(out / 'environment.json'), out, args.worker, args.arm)
        return
    if args.resume:
        env = read(out / 'environment.json')
        environment_check(env)
        if (out / 'completed.json').exists():
            for name, value in read(out / 'completed.json')['files'].items():
                if digest(out / name) != value:
                    raise ValueError('Completed result changed')
            print('Already complete: ' + str(out / 'report.md'))
            return
    else:
        if out.exists() and any(out.iterdir()):
            raise FileExistsError('Choose new output or --resume')
        fixture = args.preset == 'smoke'
        device = args.prepare_device or ('cpu' if fixture else 'cuda')
        if not fixture and device != 'cuda':
            raise ValueError('Historical preparation identity requires CUDA')
        env = dict(preset=args.preset, fixture=fixture, device=device, cases=cases(args.preset),
                   sources=sources(), runtime=runtime(), started_utc=time.time())
        out.mkdir(parents=True, exist_ok=True)
        write_new(out / 'environment.json', env)
    if not env['fixture'] and power_status()['ac_line_status'] != 1:
        raise RuntimeError('AC power required')
    with Monitor(out / f'power_{time.time_ns()}.jsonl'):
        new_runs = execute(env, out)
    environment_check(env)
    write_new(out / 'completed.json', dict(new_runs=new_runs, records=2*len(env['cases']),
              files={str(p.relative_to(out)): digest(p) for p in out.rglob('*') if p.is_file() and p.name not in ('completed.json', 'finished.json')}))
    write_new(out / 'finished.json', dict(completed_manifest_sha256=digest(out / 'completed.json')))
    print('Finished: ' + str(out / 'report.md'), flush=True)


if __name__ == '__main__':
    main()
