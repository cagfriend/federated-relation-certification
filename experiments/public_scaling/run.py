"""Fixed-private-data public sample scaling with exact B/E/D trajectory audits."""
import argparse
from dataclasses import replace
import gc
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tracemalloc

import numpy as np
from threadpoolctl import threadpool_limits

from .config import from_json, make_plan, preset
from .data import json_write_new, prepare, runtime, sha, source_hashes, verify_prepared
from .engine import METHODS, run_seed
from .report import write_reports
from .util import load_json, native_peak_bytes, seal_payload, validate_payload


def validate_environment(env):
    if env['source_hashes'] != source_hashes():
        raise ValueError('Source changed since run start; use a new output directory')
    actual = runtime()
    for name in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch'):
        if env['runtime'][name] != actual[name]:
            raise ValueError(f'Runtime changed: {name}')


def verify_marker(marker):
    directory = Path(marker['path'])
    if sha(directory / 'prepared.json') != marker['metadata_sha256']:
        raise ValueError('Prepared manifest changed')
    verify_prepared(directory, load_json(directory / 'prepared.json'))
    return directory


def checked_case(path, config, seed, directory):
    case = load_json(path)
    validate_payload(case)
    if (case['config'] != config.json() or case['seed'] != seed or case['case_id'] != config.case_id
            or case['dataset'] != 'Fashion-MNIST' or case['prepared_directory'] != str(Path(directory).resolve())
            or set(case['summary']) != set(METHODS) or not case['validation']['enabled']
            or case['validation']['mismatches'] != 0):
        raise ValueError(f'Invalid checkpoint: {path}')
    for name in METHODS:
        if sorted(r['round'] for r in case['round_records'] if r['method'] == name) != list(range(1, config.rounds + 1)):
            raise ValueError(f'Incomplete rounds: {path}')
    n, e = len(config.dimensions), config.samples * config.degree // 2
    if (case['validation']['relation_comparisons'] != 3 * config.rounds * n * e
            or case['validation']['candidate_membership_comparisons'] != 2 * config.rounds * n * config.samples):
        raise ValueError('Incorrect validation scope')
    return case


def checked_profile(profile, config, seed, expected_bytes):
    validate_payload(profile)
    if (profile['seed'] != seed or profile['case_id'] != config.case_id or profile['method'] not in METHODS
            or profile['rounds'] != config.rounds or profile['tracemalloc_peak_bytes'] <= 0
            or profile['persistent_method_array_bytes'] != expected_bytes):
        raise ValueError('Memory profile checkpoint mismatch')
    return profile


def memory_configs(plan, scope):
    if scope == 'all':
        return plan
    targets = {max(plan, key=lambda c: (c.samples, c.degree)).case_id,
               max(plan, key=lambda c: (c.degree, c.samples)).case_id}
    return [c for c in plan if c.case_id in targets]


def check_shared_cases(cases):
    by_seed = {}
    for case in cases:
        shared = (case['prepared_directory'], case['initial_head_digest'], case['shared_private_evidence'])
        if case['seed'] in by_seed and by_seed[case['seed']] != shared:
            raise ValueError('Cases did not share private data, encoder, pseudo-labels and initial heads')
        by_seed[case['seed']] = shared


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('smoke', 'full'), default='full')
    parser.add_argument('--suite', choices=('public', 'graph', 'all'), default='public')
    parser.add_argument('--download', action='store_true')
    parser.add_argument('--data-dir', type=Path, default=Path('experiments/real_iid/data'))
    parser.add_argument('--cache', type=Path, default=Path('experiments/public_scaling/prepared'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--seeds', type=int, nargs='+')
    parser.add_argument('--rounds', type=int)
    parser.add_argument('--memory-audit', action='store_true')
    parser.add_argument('--memory-scope', choices=('largest', 'all'), default='largest',
                        help='largest profiles max-M and max-degree cases; outside performance timing')
    parser.add_argument('--resume', action='store_true', help='Reuse exact saved plan; repeat only unfinished cases')
    parser.add_argument('--reuse-from', type=Path, help='Import matching completed cases from this NEW experiment only')
    parser.add_argument('--memory-worker', choices=tuple(METHODS), help=argparse.SUPPRESS)
    parser.add_argument('--worker-seed', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--worker-case', help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.output.resolve()
    if args.memory_worker:
        env = load_json(output / 'environment.json')
        config = next(from_json(v) for v in env['plan'] if from_json(v).case_id == args.worker_case)
        with threadpool_limits(limits=config.threads):
            validate_environment(env)
            directory = verify_marker(load_json(output / f'prepared_{args.worker_seed}.json'))
            tracemalloc.start()
            case = run_seed(directory, config, names=(args.memory_worker,), validate=False, progress=False)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            print(__import__('json').dumps({'seed': args.worker_seed, 'case_id': config.case_id,
                  'method': args.memory_worker, 'rounds': config.rounds, 'tracemalloc_peak_bytes': peak,
                  'process_peak_working_set_bytes': native_peak_bytes(),
                  'persistent_method_array_bytes': case['summary'][args.memory_worker]['persistent_method_array_bytes'],
                  'scope': 'isolated full head training with selected public prefix and metrics; no oracle or encoder preparation; instrumented times discarded'}))
        return
    if args.resume:
        env = load_json(output / 'environment.json')
        plan, seeds = [from_json(v) for v in env['plan']], env['seeds']
        args.cache, args.data_dir = Path(env['cache']), Path(env['data_dir'])
        print('Resuming exact saved configuration; CLI preset/suite/seed/device/round/memory overrides ignored', flush=True)
    else:
        base = replace(preset(args.preset), prepare_device=args.prepare_device)
        if args.rounds is not None:
            base = replace(base, rounds=args.rounds)
        plan = make_plan(base, args.suite)
        seeds = args.seeds if args.seeds is not None else ([404] if args.preset == 'smoke' else [404, 505, 606])
        if not seeds or len(set(seeds)) != len(seeds) or min(seeds) < 0 or max(seeds) > 2**31 - 100000:
            raise ValueError('Need distinct nonnegative seeds within 31-bit range')
        if output.exists() and any(output.iterdir()):
            raise FileExistsError('Output directory is nonempty; choose a new directory or --resume')
        output.mkdir(parents=True, exist_ok=True)
        with threadpool_limits(limits=base.threads):
            env = {'plan': [c.json() for c in plan], 'seeds': seeds, 'suite': args.suite, 'preset': args.preset,
                   'data_dir': str(args.data_dir.resolve()), 'cache': str(args.cache.resolve()),
                   'runtime': runtime(), 'source_hashes': source_hashes(),
                   'memory_audit': args.memory_audit, 'memory_scope': args.memory_scope,
                   'reuse_from': None if args.reuse_from is None else str(args.reuse_from.resolve()),
                   'execution_order': {str(seed): [plan[i].case_id for i in np.random.default_rng(
                       np.random.SeedSequence([seed, 611])).permutation(len(plan))] for seed in seeds},
                   'scope': 'Fixed private split and AE; nested public pool and graphs; serial CPU heads; in-memory messages, no real network/failover'}
        json_write_new(output / 'environment.json', env)
    base = plan[0]
    for config in plan:
        config.validate()
        if config.preparation() != base.preparation():
            raise ValueError('All cases must share one preparation policy')
    with threadpool_limits(limits=base.threads):
        validate_environment(env)
        started = time.perf_counter()
        reference = None
        if env['reuse_from']:
            reference = Path(env['reuse_from'])
            prior_env = load_json(reference / 'environment.json')
            validate_environment(prior_env)
            done = load_json(reference / 'completed.json')
            for name, expected in done['file_hashes'].items():
                if sha(reference / name) != expected:
                    raise ValueError('Reference results changed')
        cases, reused = [], []
        configs = {c.case_id: c for c in plan}
        for seed in seeds:
            record_path = output / f'prepared_{seed}.json'
            if record_path.exists():
                directory = verify_marker(load_json(record_path))
            else:
                directory = prepare(args.cache, args.data_dir, base, seed, download=args.download)
                json_write_new(record_path, {'path': str(directory.resolve()), 'metadata_sha256': sha(directory / 'prepared.json')})
                verify_marker(load_json(record_path))
            for case_id in env['execution_order'][str(seed)]:
                config = configs[case_id]
                path = output / f'{case_id}_seed_{seed}.json'
                prior = None if reference is None else reference / path.name
                if path.exists():
                    case = checked_case(path, config, seed, directory)
                    print(f'Preserved {case_id} seed={seed}', flush=True)
                elif prior is not None and prior.exists():
                    case = checked_case(prior, config, seed, directory)
                    shutil.copyfile(prior, path)
                    reused.append({'case_id': case_id, 'seed': seed, 'source': str(prior), 'sha256': sha(prior)})
                    print(f'Reused {case_id} seed={seed}', flush=True)
                else:
                    print(f'Training {case_id} seed={seed}: fixed private set, real B/E/D SGD', flush=True)
                    with threadpool_limits(limits=config.threads):
                        case = seal_payload(run_seed(directory, config))
                    json_write_new(path, case)
                    checked_case(path, config, seed, directory)
                cases.append(case)
                check_shared_cases(cases)
                write_reports(output, cases, [])
                gc.collect()
        profiles = []
        if env['memory_audit']:
            for seed in seeds:
                for config in memory_configs(plan, env['memory_scope']):
                    for method in METHODS:
                        path = output / f'memory_{config.case_id}_{method}_{seed}.json'
                        if path.exists():
                            profile = load_json(path)
                        else:
                            worker = subprocess.run([sys.executable, '-m', 'experiments.public_scaling.run',
                                '--output', str(output), '--memory-worker', method, '--worker-seed', str(seed),
                                '--worker-case', config.case_id], check=True, capture_output=True, text=True)
                            profile = seal_payload(__import__('json').loads(worker.stdout))
                            json_write_new(path, profile)
                        expected = next(c for c in cases if c['seed'] == seed and c['case_id'] == config.case_id)['summary'][method]['persistent_method_array_bytes']
                        if profile.get('method') != method:
                            raise ValueError('Memory checkpoint method mismatch')
                        profiles.append(checked_profile(profile, config, seed, expected))
                        print(f'Memory complete: {config.case_id} seed={seed} {method}', flush=True)
        # Preserve reuse provenance across a later --resume.
        provenance_path = output / 'reused_cases.json'
        previous = load_json(provenance_path) if provenance_path.exists() else []
        provenance = {str(v['source']): v for v in previous + reused}
        provenance_path.write_text(__import__('json').dumps(list(provenance.values()), indent=2), encoding='utf-8')
        (output / 'memory.json').write_text(__import__('json').dumps(profiles, indent=2), encoding='utf-8')
        write_reports(output, cases, profiles)
        validate_environment(env)
        completed = {'seeds': seeds, 'case_count': len(cases), 'method_runs': len(cases) * len(METHODS),
                     'memory_profiles': len(profiles), 'mismatches': 0, 'source_hashes': source_hashes(),
                     'invocation_wall_seconds': time.perf_counter() - started,
                     'note': 'Invocation includes paired cases, preparation, oracle, metrics and memory replays; not a method latency',
                     'file_hashes': {p.name: sha(p) for p in sorted(output.glob('*.json')) if p.name != 'completed.json'}}
        (output / 'completed.json').write_text(__import__('json').dumps(completed, indent=2), encoding='utf-8')
        print(f'Complete: {output / "report.md"}', flush=True)


if __name__ == '__main__':
    main()
