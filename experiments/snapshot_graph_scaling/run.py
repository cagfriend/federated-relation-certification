"""Audit and time three nested public bank sizes under E38 training."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

for var in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[var] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (ROOT, checkpoints, environment, history_pair,
    read, receipt, require, seal, sealed, sha, sources, write)
from experiments.snapshot_certification_timing.inputs import load_verified
from .design import SIZES, cell_id, configs, context_id, run_path, schedule
from .inputs import choose_bank, raw_sha
from .report import build
from .worker import run

PACKAGE = ROOT/'experiments/snapshot_graph_scaling'
SOURCE = ROOT/'experiments/snapshot_external_comparison'
TIMING = ROOT/'experiments/snapshot_certification_timing'


def pair(a, b):
    same = a['case']['method'] == b['case']['method']
    require(all(a[k] == b[k] for k in ('cfg', 'initial', 'traffic', 'evaluations', 'protocol_bytes')),
            f"Init, quality or traffic mismatch: {b['case']}")
    ignored = {'seconds', 'timing_parts', 'private_seconds', 'generation_seconds', 'exchange_seconds', 'public_seconds'}
    if not same:
        ignored |= {'endpoint_counts', 'certified_edges'}
    else:
        require(a['cache_bytes'] == b['cache_bytes'], 'Certification cache size changed')
    for x, y in zip(a['rows'], b['rows'], strict=True):
        require({k: v for k, v in x.items() if k not in ignored} == {k: v for k, v in y.items() if k not in ignored},
                f"Trajectory mismatch: {b['case']}, round {x['round']}")


def verify(path, case, preset, identity):
    r = sealed(path)
    _, cfg = configs(preset, case)
    n = cfg['rounds']
    require(r['manifest_sha256'] == identity and r['case'] == case and r['cfg'] == cfg and
            [x['round'] for x in r['rows']] == list(range(1,n+1)) and
            [x['round'] for x in r['evaluations']] == checkpoints(cfg), f'Invalid run {path}')
    expected = n * len(cfg['widths']) * cfg['public_size']//2 if case['stage'] == 'audit' else 0
    require(r['audit_edges'] == expected, 'Audit coverage changed')
    return r


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--stage', choices=('all', 'audit', 'timing'), default='all')
    parser.add_argument('--history', type=Path)
    parser.add_argument('--timing-reference', type=Path, help='Completed M=512 timing run (selected snapshots)')
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'experiments/stl10_transfer/data/stl10_binary')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    full = opts.preset == 'full'
    history = (opts.history or SOURCE/('results_full' if full else 'results_smoke_final')).resolve()
    ref = (opts.timing_reference or (TIMING/'results_full' if full else
                                    ROOT/'outputs/e38_cert_timing_final_smoke')).resolve()
    cache = (opts.cache or history/'cache').resolve()
    binary = (opts.data_dir/'unlabeled_X.bin').resolve() if full else None
    out = (opts.output or PACKAGE/f'results_{opts.preset}').resolve()
    require(not any(out.is_relative_to(x) or x.is_relative_to(out) for x in
                    (history, ref, cache, *((binary.parent,) if binary else ()))), 'Output overlaps an input')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, history, ref, cache, binary)


def execute(opts, out, history, ref, cache, binary):
    cases = schedule(opts.preset)
    manifest_path = out/'manifest.json'
    prep_dir = ref/'preparation'
    prep_lock = sealed(ref/'prepared.json')
    ref_done = sealed(ref/'completed.json')
    ref_id = sha(ref/'manifest.json')
    require(prep_lock['manifest_sha256'] == ref_done['manifest_sha256'] == ref_id and
            ref_done['audit_passed_sha256'] == sha(ref/'audit_passed.json'),
            'Reference completion does not match its input or audit receipts')

    def context(c):
        base, cfg = configs(opts.preset, c)
        old, anchors = history_pair(history, base, c['partition'])
        cid = context_id(c)
        prep_path = prep_dir/f'{cid}.json'
        require(prep_lock['hashes'][cid] == sha(prep_path), 'Selected snapshot receipt changed')
        return base, cfg, old, anchors, prep_path

    if opts.worker is not None:
        m = read(manifest_path)
        identity = sha(manifest_path)
        c = cases[opts.worker]
        require(m['schedule'][opts.worker] == c and m['environment'] == environment() and
                m['reference_manifest'] == ref_id, 'Worker environment or schedule changed')
        base, cfg, old, anchors, prep_path = context(c)
        require(m['history'][context_id(c)] == anchors and m['preparation'][context_id(c)] == sha(prep_path),
                'Preparation/history identity differs in worker')
        if c['stage'] == 'timing':
            require(sealed(out/'audit_passed.json')['manifest_sha256'] == identity, 'Audit must pass before timing')
        bank_path = out/'banks'/f'{c["seed"]}.json'
        lock = sealed(out/'banks_sealed.json')
        require(lock['manifest_sha256'] == identity and lock['banks'][str(c['seed'])] == sha(bank_path),
                'Public bank is not sealed for this run')
        bank = sealed(bank_path)
        r = run(out, c, base, cfg, prep_dir, cache/str(c['seed']), old, anchors, bank)
        seal(out/run_path(c), dict(manifest_sha256=identity, **r))
        return

    contexts, raw_digest = {}, None
    if binary:
        require(binary.is_file(), f'Missing raw STL-10 unlabeled file: {binary}')
        print('Checking the original STL-10 public data file ...', flush=True)
        raw_digest = raw_sha(binary)
    for c in cases:
        cid = context_id(c)
        if cid not in contexts:
            contexts[cid] = (c, *context(c))
    m = dict(preset=opts.preset, schedule=cases, raw_file=str(binary) if binary else None, raw_sha256=raw_digest,
             history_root=str(history), reference_root=str(ref), cache=str(cache), reference_manifest=ref_id,
             history={k: x[4] for k, x in contexts.items()}, preparation={k: sha(x[5]) for k, x in contexts.items()},
             environment=environment(), source_hashes=sources(), design_sha256=sha(PACKAGE/'README.md'))
    if manifest_path.exists():
        require(opts.resume and read(manifest_path) == m, 'Resume requires identical code and inputs')
    else:
        require(opts.stage != 'timing' and (not out.exists() or not any(out.iterdir())),
                'Start with a fresh audit or use --resume with existing runs')
        write(manifest_path, m)
    identity = sha(manifest_path)
    banks = {}
    for c, base, _, old, _, _ in contexts.values():
        seed = c['seed']
        _, train, _ = load_verified(cache/str(seed), c['partition'], base, old)
        path = out/'banks'/f'{seed}.json'
        if seed not in banks:
            print(f'Preparing nested public bank for seed {seed} ...', flush=True)
        choose_bank(out, seed, train, max(SIZES[opts.preset]), binary, raw_digest)
        banks[seed] = sha(path)
    bank_lock = out/'banks_sealed.json'
    bank_record = dict(manifest_sha256=identity, banks={str(k): v for k, v in banks.items()})
    if bank_lock.exists():
        require(sealed(bank_lock) == bank_record, 'Public bank changed')
    else:
        require(not (out/'audit').exists() and not (out/'timing').exists(), 'Missing public bank receipt')
        seal(bank_lock, bank_record)

    def get(index, c, launch):
        path = out/run_path(c)
        if launch and not receipt(path).exists():
            print(f'{index+1}/{len(cases)} {run_path(c)}', flush=True)
            command = [sys.executable, '-B', '-m', 'experiments.snapshot_graph_scaling.run',
                       '--preset', opts.preset, '--output', str(out), '--history', str(history),
                       '--timing-reference', str(ref), '--cache', str(cache), '--worker', str(index)]
            if binary:
                command.extend(['--data-dir', str(binary.parent)])
            subprocess.run(command, cwd=ROOT, check=True)
        return verify(path, c, opts.preset, identity)

    audit_runs, audited_path = {}, out/'audit_passed.json'
    initial = {}
    for i, c in enumerate(cases):
        if c['stage'] != 'audit':
            continue
        r = get(i, c, opts.stage in ('all', 'audit'))
        group = audit_runs.setdefault(cell_id(c), {})
        if 'B' in group:
            pair(group['B'], r)
        group[c['method']] = r
        key = {k: r['initial'][k] for k in ('model_digest', 'head_digest', 'centers', 'pseudo')}
        require(initial.setdefault(context_id(c), key) == key, 'Across-size initial head or fixed input changed')
    audited = dict(manifest_sha256=identity, hashes={run_path(c): sha(out/run_path(c))
                                                    for c in cases if c['stage'] == 'audit'})
    if audited_path.exists():
        require(sealed(audited_path) == audited, 'Audit receipts changed')
    else:
        require(opts.stage != 'timing', 'Run and seal audits before timing')
        seal(audited_path, audited)
    print('Audit passed.', flush=True)
    if opts.stage == 'audit':
        return
    done = out/'completed.json'
    previous = sealed(done) if done.exists() else None
    results, hashes = [], {}
    for i, c in enumerate(cases):
        if c['stage'] != 'timing':
            continue
        key = run_path(c)
        if previous:
            require(previous['hashes'][key] == sha(out/key), 'Previously completed run changed')
        r = get(i, c, True)
        pair(audit_runs[cell_id(c)][c['method']], r)
        results.append(r)
        hashes[key] = sha(out/key)
    common = {k: sealed(x[5]) for k, x in contexts.items()}
    build(out, results, common, smoke=opts.preset == 'smoke')
    seal(done, dict(manifest_sha256=identity, audit_sha256=sha(audited_path), hashes=hashes))
    print(f'Finished: {out/"report.md"}', flush=True)


if __name__ == '__main__':
    main()
