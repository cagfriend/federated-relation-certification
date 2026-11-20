"""Run an untimed audit first, then sealed, paired B/E/D timing blocks."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

# Set before importing native runtimes, in both parent and worker.
for var in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[var] = '1'

import torch
from threadpoolctl import threadpool_limits

from .design import (PLAN, ROOT, case_id, cfg_for, checkpoints, environment, history_pair,
                     path_for, read, receipt, require, schedule, seal, sealed, sha, sources, write)
from .inputs import cache_location, preparation, verify_preparation
from .report import build, run_metrics
from .worker import run

SHARED_ROW = ('round', 'head_digest', 'head_by_client', 'teachers_by_client', 'relation_digests',
              'aggregate_digest', 'consumed_target_digests', 'public_orders', 'public_steps_by_client',
              'private_losses', 'public_losses', 'teacher_positive_rates', 'aggregate_positive_rate',
              'traffic_delta', 'teacher_motion')


def verify_run(out, case, manifest_sha, cfg, *, rerun=None):
    path = path_for(out, case)
    result = sealed(path)
    n = cfg['rounds']
    require(result['case'] == case and result['cfg'] == cfg and result['manifest_sha256'] == manifest_sha and
            result.get('rerun_id') == rerun and
            [r['round'] for r in result['rows']] == list(range(1, n+1)) and
            [r['round'] for r in result['evaluations']] == checkpoints(cfg), f'Invalid run: {path}')
    require(result['audit_edges'] == (n*len(cfg['widths'])*cfg['public_size']//2
                                      if case['stage'] == 'audit' else 0), f'Audit coverage mismatch: {path}')
    return result


def compare(a, b, *, same_method=False, both_audited=False):
    ident = case_id(b['case']) + '/' + b['case']['method']
    require(all(a[k] == b[k] for k in ('cfg', 'initial', 'evaluations', 'traffic')), f'Init/eval/traffic mismatch: {ident}')
    keys = SHARED_ROW + (('audited_private_orders',) if both_audited else ())
    if same_method:
        keys += ('endpoint_counts', 'certified_edges')
        require(a['cache_bytes'] == b['cache_bytes'], f'Cache size changed: {ident}')
    for x, y in zip(a['rows'], b['rows'], strict=True):
        for k in keys:
            require(x[k] == y[k], f'{ident}, round {x["round"]}: {k} mismatch')


def audit_gate(out, cases, manifest_sha, configs, *, finish=False):
    audit_cases = [c for c in cases if c['stage'] == 'audit']
    refs = {}
    for case in audit_cases:
        key = case_id(case)
        result = verify_run(out, case, manifest_sha, configs[key])
        group = refs.setdefault(key, {})
        if 'B' in group:
            compare(group['B'], result, both_audited=True)
        group[case['method']] = result
    payload = dict(manifest_sha256=manifest_sha,
                   hashes={path_for(out, c).name: sha(path_for(out, c)) for c in audit_cases})
    path = out/'audit_passed.json'
    if finish and not path.exists():
        seal(path, payload)
    else:
        require(sealed(path) == payload, 'Audit pass receipt or verified inputs changed')
    return refs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preset', choices=['full', 'smoke'], default='full')
    p.add_argument('--stage', choices=['audit', 'timing', 'all'], default='all')
    p.add_argument('--history', type=Path, help='E38 results with archived runs and receipts')
    p.add_argument('--cache', type=Path, help='E38 cache root (per-seed folders); defaults to history/cache')
    p.add_argument('--data-dir', type=Path, help='STL-10 binary directory, only used to recreate missing cache')
    p.add_argument('--output', type=Path)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--rerun-block', help='Confirmed disturbance only: case:repeat, e.g. 1201_iid:2')
    p.add_argument('--reason', help='Reason for a confirmed pause, sleep or timing interruption')
    p.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    p.add_argument('--rerun-id', type=int, help=argparse.SUPPRESS)
    args = p.parse_args()
    if args.rerun_block and (args.preset != 'full' or not args.reason or not args.reason.strip() or not args.resume):
        p.error('--rerun-block requires --preset full, --resume and a nonempty --reason')
    smoke = args.preset == 'smoke'
    history = (args.history or ROOT/'experiments/snapshot_external_comparison'/
               ('results_smoke_final' if smoke else 'results_full')).resolve()
    cache = (args.cache or history/'cache').resolve()
    out = (args.output or ROOT/f'experiments/snapshot_certification_timing/results_{args.preset}').resolve()
    data = args.data_dir.resolve() if args.data_dir else None
    require(not any(out.is_relative_to(x) or x.is_relative_to(out) for x in (history, cache, data) if x),
            'Output would overlap an input')
    cases = list(schedule(args.preset))
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(args, cases, history, cache, data, out)


def execute(args, cases, history, cache, data, out):
    manifest_path = out/'manifest.json'
    if args.worker is not None:
        manifest = read(manifest_path)
        require(environment() == manifest['environment'], 'Worker environment differs from manifest')
        c = cases[args.worker]
        require(c == manifest['schedule'][args.worker], 'Worker schedule differs from manifest')
        if c['stage'] == 'timing':
            passed = sealed(out/'audit_passed.json')
            require(passed['manifest_sha256'] == sha(manifest_path), 'Audit receipt belongs to a different run')
        cid = case_id(c)
        cfg = cfg_for(args.preset, c['seed'])
        old, anchors = history_pair(history, cfg, c['partition'])
        require(manifest['anchors'][cid] == anchors, 'Worker historical input changed')
        path = out/'preparation'/f'{cid}.json'
        mh = sha(manifest_path)
        prep_gate = sealed(out/'prepared.json')
        require(prep_gate['manifest_sha256'] == mh and prep_gate['hashes'][cid] == sha(path),
                'Prepared input no longer matches the sealed preparation')
        prep = verify_preparation(path, path.with_suffix('.pt'), Path(manifest['cache_roots'][cid]), cfg, old, anchors)
        dest = out
        if args.rerun_id is not None:
            dest = out/'reruns'/f'{args.rerun_id:03d}'
            require(c in sealed(dest/'request.json')['cases'], 'Rerun request does not contain case')
        seal(path_for(dest, c), dict(manifest_sha256=mh, rerun_id=args.rerun_id, **run(out, c, cfg, old, prep)))
        return
    contexts = {}
    for c in cases:
        cid = case_id(c)
        if cid not in contexts:
            cfg = cfg_for(args.preset, c['seed'])
            old, anchors = history_pair(history, cfg, c['partition'])
            original = cache/str(cfg['seed'])
            remade = out/'recreated_cache'/str(cfg['seed'])
            directory = original if (original/c['partition']/'manifest.json').exists() else remade
            contexts[cid] = (c, cfg, old, anchors, directory)
    manifest = dict(preset=args.preset, history=str(history), cache=str(cache), data=str(data) if data else None,
                    history_manifest=sha(history/'manifest.json'), history_completion=sha(history/'completed.json'),
                    schedule=cases, configs={k: x[1] for k, x in contexts.items()},
                    anchors={k: x[3] for k, x in contexts.items()},
                    cache_roots={k: str(x[4]) for k, x in contexts.items()},
                    environment=environment(), sources=sources(), design_sha256=sha(PLAN))
    if manifest_path.exists():
        require(args.resume and read(manifest_path) == manifest, 'Use --resume with identical inputs or a new output')
    else:
        require(args.stage != 'timing', 'Run the audit first in this output directory')
        require(not out.exists() or not any(out.iterdir()), 'Output must be new or empty')
        write(manifest_path, manifest)
    mh = sha(manifest_path)
    prep_lock = out/'prepared.json'
    prepared = sealed(prep_lock) if prep_lock.exists() else None
    require(prepared is not None or not ((out/'audit').exists() or (out/'timing').exists()),
            'Existing runs are missing the preparation receipt')
    if prepared is not None:
        require(prepared['manifest_sha256'] == mh and set(prepared['hashes']) == set(contexts) and all(
            sha(out/'preparation'/f'{cid}.json') == h for cid, h in prepared['hashes'].items()),
            'Prepared inputs changed')
    preps = {}
    for cid, (c, cfg, old, anchors, directory) in contexts.items():
        loaded = cache_location(cache, out, cfg, c['partition'], data)
        require(loaded == directory, 'Cache source changed')
        preps[cid] = preparation(out, c, cfg, directory, old, anchors)
    if prepared is None:
        seal(prep_lock, dict(manifest_sha256=mh, hashes={cid: sha(out/'preparation'/f'{cid}.json') for cid in preps}))

    def run_or_resume(index, case, dest=out, rerun=None):
        if not receipt(path_for(dest, case)).exists():
            print(f"{index+1}/{len(cases)} {case['stage']} {case_id(case)} {case['method']} r{case['repeat']}", flush=True)
            command = [sys.executable, '-B', '-m', 'experiments.snapshot_certification_timing.run',
                       '--preset', args.preset, '--history', str(history), '--cache', str(cache),
                       '--output', str(out), '--worker', str(index)]
            if rerun is not None:
                command.extend(['--rerun-id', str(rerun)])
            subprocess.run(command, cwd=ROOT, check=True)
        return verify_run(dest, case, mh, manifest['configs'][case_id(case)], rerun=rerun)

    cfgs = manifest['configs']
    if args.rerun_block:
        require((out/'completed.json').is_file(), 'Finish the original run before an explicitly requested block rerun')
        refs = audit_gate(out, cases, mh, cfgs)
        indexed = [(i, c) for i, c in enumerate(cases) if c['stage'] == 'timing' and
                   f"{case_id(c)}:{c['repeat']}" == args.rerun_block]
        require(len(indexed) == 3, 'Unknown timing block')
        request = dict(block=args.rerun_block, reason=args.reason, cases=[c for _, c in indexed], manifest_sha256=mh)
        rerun_root = out/'reruns'
        ids = sorted(int(x.name) for x in rerun_root.glob('[0-9][0-9][0-9]') if x.is_dir())
        retry = next((rid for rid in reversed(ids)
                      if not (rerun_root/f'{rid:03d}'/'completed.json').exists()
                      and sealed(rerun_root/f'{rid:03d}'/'request.json') == request), None)
        if retry is None:
            retry = max(ids, default=0)+1
            seal(rerun_root/f'{retry:03d}'/'request.json', request)
        dest = rerun_root/f'{retry:03d}'
        replacement = []
        for i, c in indexed:
            result = run_or_resume(i, c, dest, retry)
            compare(refs[case_id(c)][c['method']], result, same_method=True)
            replacement.append(result)
        original = [verify_run(out, c, mh, cfgs[case_id(c)]) for _, c in indexed]
        common = preps[case_id(indexed[0][1])]
        write(dest/'comparison.json', dict(request=request, original=[run_metrics(r, common) for r in original],
                                          rerun=[run_metrics(r, common) for r in replacement]))
        seal(dest/'completed.json', dict(request=request, hashes={path_for(dest, c).name: sha(path_for(dest, c))
                                                                   for _, c in indexed}))
        print(f'Finished separate block rerun: {dest}', flush=True)
        return

    if args.stage in ('all', 'audit'):
        for i, c in enumerate(cases):
            if c['stage'] == 'audit':
                run_or_resume(i, c)
        audit_gate(out, cases, mh, cfgs, finish=True)
        print('Audit passed.', flush=True)
    if args.stage in ('all', 'timing'):
        refs = audit_gate(out, cases, mh, cfgs)
        results = []
        completed = out/'completed.json'
        prior = sealed(completed) if completed.exists() else None
        for i, c in enumerate(cases):
            if c['stage'] == 'timing':
                if prior:
                    path = path_for(out, c)
                    require(prior['timing_runs'][path.name] == sha(path), 'Completed result changed')
                result = run_or_resume(i, c)
                compare(refs[case_id(c)][c['method']], result, same_method=True)
                results.append(result)
        build(out, results, preps, smoke=args.preset == 'smoke')
        seal(completed, dict(manifest_sha256=mh, audit_passed_sha256=sha(out/'audit_passed.json'),
                             timing_runs={path_for(out, c).name: sha(path_for(out, c))
                                          for c in cases if c['stage'] == 'timing'}))
        print(f'Finished: {out/"report.md"}', flush=True)


if __name__ == '__main__':
    main()
