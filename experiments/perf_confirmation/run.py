"""Independent-process performance confirmation (NEXT_EXPERIMENTS item 2).

Each B/E/D run executes in its own subprocess via the frozen
private_workload training implementation; the parent only schedules
(balanced order), verifies trajectory identity across methods/repeats,
and reports. Design and decision rules: PREREGISTRATION.md.
"""
import argparse
from collections import Counter
import json, math, subprocess, sys, time
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.public_scaling.data import sha, runtime, source_hashes
from experiments.public_scaling.util import load_json, seal_payload, validate_payload, native_peak_bytes
from experiments.noniid_clustering.data import prepare, verify, ensure_data
from experiments.private_workload.design import spec_from_json
from .design import PARTITIONS, METHODS, REPEATS, DECISION, PRIMARY_PRIVATE_LIMIT, plan, seeds_for, schedule, run_filename
from .engine import run_single, check_block_identity, TRAJECTORY_KEYS
from .report import reports

ROOT = Path(__file__).resolve().parents[2]
DESIGN = dict(stage='Independent performance confirmation of the frozen private-workload candidate',
    methods=list(METHODS), partitions=list(PARTITIONS),
    confirm_seeds=[707, 808, 909], repeats=list(REPEATS),
    tiers=['privfull', f'priv{PRIMARY_PRIVATE_LIMIT}'],
    primary_metric='head_pipeline_seconds (in-process, initialization included)',
    primary_tier_private_limit=PRIMARY_PRIVATE_LIMIT,
    decision_rules=dict(db_head_ratio_median_max=DECISION['db_head_ratio_median_max'],
                        de_head_ratio_median_max=DECISION['de_head_ratio_median_max'],
                        min_seed_wins=DECISION['min_seed_wins']),
    execution='One method per independent OS process; serial; balanced method order; threads=1',
    scope='New-seed independent-process paired timing confirmation; not parallel-system latency',
    preregistration='experiments/perf_confirmation/PREREGISTRATION.md')

def own_sources(): return {p.name: sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
def dep_sources(): return {p.name: sha(p) for p in sorted((ROOT / 'experiments/private_workload').glob('*.py'))}
def prep_sources(): return {p.name: sha(p) for p in sorted((ROOT / 'experiments/noniid_clustering').glob('*.py'))}

def check_environment(env):
    if env['source_hashes'] != own_sources() or env['dependency_source_hashes'] != dep_sources() or env['core_source_hashes'] != source_hashes() or env['preparation_source_hashes'] != prep_sources():
        raise ValueError('Frozen source changed')
    if env['design'] != DESIGN:
        raise ValueError('Design changed')
    current = runtime()
    if any(current[k] != env['runtime'][k] for k in ('python', 'executable', 'numpy', 'scipy', 'sklearn', 'torch')):
        raise ValueError('Runtime changed')
    expected = [s.json() for s in plan(env['preset'], env['plan'][0]['config']['prepare_device'])]
    if env['plan'] != expected:
        raise ValueError('Plan changed')

def save(path, data):
    if path.exists():
        raise FileExistsError(path)
    tmp = path.with_suffix(path.suffix + '.part')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    tmp.replace(path)

def check_run(run, spec, part, seed, env, directory, meta):
    """Validate one single-method run record (after sealing)."""
    validate_payload(run)
    cfg = spec.config; n = len(cfg.dimensions); e = cfg.samples * cfg.degree // 2
    if (run['identity'] != env or run['partition'] != part or run['seed'] != seed
            or run['spec'] != spec.json() or run['config'] != cfg.json()
            or run['case_id'] != spec.case_id or run['method'] != meta['method']
            or run['repeat'] != meta['repeat'] or run['triple'] != meta['triple']
            or run['position'] != meta['position'] or run['dataset'] != 'Fashion-MNIST'
            or run['prepared_directory'] != str(directory.resolve())):
        raise ValueError('Run identity differs')
    rr = run['round_records']
    if [r['round'] for r in rr] != list(range(1, cfg.rounds + 1)) or any(r['method'] != meta['method'] for r in rr):
        raise ValueError('Incomplete round coverage')
    for r in rr:
        for k in TRAJECTORY_KEYS:
            if k not in r:
                raise ValueError('Missing trajectory field ' + k)
        for phase in ('private', 'generation', 'exchange', 'public', 'pipeline'):
            if not math.isfinite(r[phase + '_seconds']) or r[phase + '_seconds'] < 0:
                raise ValueError('Invalid timing')
    s = run['summary'][meta['method']]
    pipeline = s['initialization_seconds'] + sum(r['pipeline_seconds'] for r in rr)
    if abs(s['head_pipeline_seconds'] - pipeline) > 1e-8:
        raise ValueError('Summary timing differs')
    for phase in ('private', 'generation', 'exchange', 'public'):
        if abs(s[phase + '_seconds'] - sum(r[phase + '_seconds'] for r in rr)) > 1e-8:
            raise ValueError('Phase summary differs')
    if s['final_head_digest'] != rr[-1]['head_digest_after_public']:
        raise ValueError('Final digest differs')
    if s['final_metrics'] is None or s['final_metrics']['round'] != cfg.rounds:
        raise ValueError('Final metrics missing')
    v = run['validation']
    # The oracle audits candidate sets only for E/D; B contributes none.
    expected_candidates = 0 if meta['method'] == 'B' else cfg.rounds * n * cfg.samples
    if not v['enabled'] or v['mismatches'] != 0 or v['relation_comparisons'] != cfg.rounds * n * e \
            or v['candidate_membership_comparisons'] != expected_candidates:
        raise ValueError('Wrong oracle coverage')
    if not (run['process_wall_seconds'] > 0 and run['process_peak_bytes'] > 0):
        raise ValueError('Process record missing')
    return True

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preset', choices=('full', 'smoke'), default='full')
    ap.add_argument('--prepare-device', choices=('cpu', 'cuda'))
    ap.add_argument('--download', action='store_true')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--cache', type=Path, default=ROOT / 'experiments/noniid_clustering/prepared')
    ap.add_argument('--data-dir', type=Path, default=ROOT / 'experiments/real_iid/data')
    ap.add_argument('--output', type=Path)
    ap.add_argument('--worker-run', action='store_true', help=argparse.SUPPRESS)
    ap.add_argument('--worker-partition', choices=PARTITIONS, help=argparse.SUPPRESS)
    ap.add_argument('--worker-seed', type=int, help=argparse.SUPPRESS)
    ap.add_argument('--worker-case', help=argparse.SUPPRESS)
    ap.add_argument('--worker-method', choices=METHODS, help=argparse.SUPPRESS)
    ap.add_argument('--worker-repeat', type=int, help=argparse.SUPPRESS)
    args = ap.parse_args()
    output = (args.output or ROOT / f'experiments/perf_confirmation/results_{args.preset}').resolve()
    runs_dir = output / 'runs'

    if args.worker_run:
        env = load_json(output / 'environment.json'); check_environment(env)
        spec = next(s for s in map(spec_from_json, env['plan']) if s.case_id == args.worker_case)
        marker = load_json(output / f'prepared_{args.worker_partition}_seed_{args.worker_seed}.json')
        directory = Path(marker['path'])
        if sha(directory / 'prepared.json') != marker['metadata_sha256']:
            raise ValueError('Prepared marker changed')
        verify(directory, spec.config, args.worker_seed, args.worker_partition)
        with threadpool_limits(limits=spec.config.threads):
            result = run_single(directory, spec, args.worker_method)
        result['partition'] = args.worker_partition
        target = runs_dir / f'pending_{args.worker_partition}_{args.worker_case}_seed_{args.worker_seed}_{args.worker_method}_rep{args.worker_repeat}.json'
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
        print(json.dumps(dict(process_peak_bytes=native_peak_bytes(),
                              final_head_digest=result['summary'][args.worker_method]['final_head_digest'])))
        return

    if args.resume:
        env = load_json(output / 'environment.json'); check_environment(env)
        specs = [spec_from_json(v) for v in env['plan']]
        args.cache = Path(env['cache']); args.data_dir = Path(env['data_dir'])
        print('Resume uses frozen plan and sources', flush=True)
    else:
        if output.exists() and any(output.iterdir()):
            raise FileExistsError('Use new output or --resume')
        specs = plan(args.preset, args.prepare_device)
        env = dict(preset=args.preset, plan=[s.json() for s in specs], design=DESIGN,
                   source_hashes=own_sources(), dependency_source_hashes=dep_sources(),
                   core_source_hashes=source_hashes(), preparation_source_hashes=prep_sources(),
                   runtime=runtime(), cache=str(args.cache.resolve()), data_dir=str(args.data_dir.resolve()))
        output.mkdir(parents=True, exist_ok=True); runs_dir.mkdir(exist_ok=True)
        save(output / 'environment.json', env)
    spec_by_case = {s.case_id: s for s in specs}
    sched = schedule(env['preset'])
    expected_runs = len(seeds_for(env['preset'])) * len(PARTITIONS) * len(specs) * len(METHODS) * len(REPEATS)
    if len(sched) != expected_runs:
        raise AssertionError('Schedule size differs from preregistration')
    ensure_data(args.data_dir, args.download)
    markers = {}
    runs = []; blocks_done = 0; block_keys = []
    for seed in seeds_for(env['preset']):
        for part in PARTITIONS:
            markerpath = output / f'prepared_{part}_seed_{seed}.json'
            if markerpath.exists():
                marker = load_json(markerpath); directory = Path(marker['path'])
                if sha(directory / 'prepared.json') != marker['metadata_sha256']:
                    raise ValueError('Prepared identity changed')
            else:
                directory = prepare(args.cache, args.data_dir, specs[0].config, seed, part, download=args.download)
                save(markerpath, dict(path=str(directory.resolve()), metadata_sha256=sha(directory / 'prepared.json')))
            verify(directory, specs[0].config, seed, part)
            markers[(part, seed)] = directory
    for spec in specs:
        for part in PARTITIONS:
            for seed in seeds_for(env['preset']):
                block_keys.append((part, seed, spec.case_id))
    done_blocks = set()
    for meta in sched:
        spec = spec_by_case[meta['case_id']]; part = meta['partition']; seed = meta['seed']
        directory = markers[(part, seed)]
        path = runs_dir / run_filename(meta)
        if path.exists():
            run = load_json(path); check_run(run, spec, part, seed, env, directory, meta)
            print(f"  preserved completed run {path.name}", flush=True)
        else:
            print(f"{part} {meta['case_id']} seed={seed} method={meta['method']} rep={meta['repeat']} "
                  f"(triple {meta['triple']}, position {meta['position']})", flush=True)
            cmd = [sys.executable, '-m', 'experiments.perf_confirmation.run', '--output', str(output),
                   '--worker-run', '--worker-partition', part, '--worker-seed', str(seed),
                   '--worker-case', meta['case_id'], '--worker-method', meta['method'],
                   '--worker-repeat', str(meta['repeat'])]
            start = time.perf_counter()
            worker = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
            wall = time.perf_counter() - start
            if worker.returncode:
                raise RuntimeError('Confirmation worker failed: ' + worker.stderr)
            info = json.loads(worker.stdout.strip().splitlines()[-1])
            pending = runs_dir / f"pending_{part}_{meta['case_id']}_seed_{seed}_{meta['method']}_rep{meta['repeat']}.json"
            run = load_json(pending)
            run.update(partition=part, triple=meta['triple'], position=meta['position'],
                       repeat=meta['repeat'], identity=env,
                       process_wall_seconds=wall, process_peak_bytes=info['process_peak_bytes'])
            if run['summary'][meta['method']]['final_head_digest'] != info['final_head_digest']:
                raise ValueError('Worker digest line differs')
            run = seal_payload(run)
            check_run(run, spec, part, seed, env, directory, meta)
            save(path, run); pending.unlink()
        runs.append(run)
        key = (part, seed, meta['case_id'])
        block = [r for r in runs if (r['partition'], r['seed'], r['case_id']) == key]
        if len(block) == 6 and key not in done_blocks:
            check_block_identity(block); done_blocks.add(key); blocks_done += 1
            print(f'  block verified: {key[0]} {key[2]} seed={key[1]} (6 runs, trajectory identical)', flush=True)
            reports(output, runs, dict(blocks_checked=blocks_done, mismatches=0),
                    expected_seeds=len(seeds_for(env['preset'])))
    check_environment(env)
    if len(done_blocks) != len(block_keys):
        raise AssertionError('Not all blocks verified')
    done = dict(run_count=len(runs), blocks_verified=blocks_done,
                training_trajectories=len({(r['partition'], r['seed'], r['case_id']) for r in runs}),
                mismatches=0,
                relation_comparisons=sum(r['validation']['relation_comparisons'] for r in runs),
                candidate_membership_comparisons=sum(r['validation']['candidate_membership_comparisons'] for r in runs),
                files={p.name: sha(p) for p in output.iterdir() if p.is_file() and p.name != 'completed.json' and not p.name.endswith('.part')})
    tmp = output / 'completed.json.part'; tmp.write_text(json.dumps(done, indent=2), encoding='utf-8'); tmp.replace(output / 'completed.json')
    print(f'Finished: {output / "report.md"}', flush=True)

if __name__ == '__main__':
    main()
