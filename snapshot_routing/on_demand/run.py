"""Compare full-graph paths with exact Demand on the E42/E43 configurations."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

for var in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[var] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (
    ROOT, checkpoints, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import raw_sha, verify_bank

from ..confirmation.run import config
from ..full_training import worker as full_worker
from ..full_training.run import reference
from .report import report
from .worker import run as demand_run, student_trace

METHODS = ('B', 'E', 'D', 'Demand')
PACKAGE = Path(__file__).resolve().parent


def schedule(preset):
    size = 4096 if preset == 'full' else 128
    cases = [dict(seed=2021, partition=p, public_size=size) for p in ('iid', 'dirichlet_0.1')]
    repeats = 3 if preset == 'full' else 1
    groups = []
    for repeat in range(1, repeats+1):
        offset = repeat-1
        order = METHODS[offset:] + METHODS[:offset]
        for i in ((0, 1) if repeat % 2 else (1, 0)):
            groups.append(dict(case=cases[i], repeat=repeat, order=list(order if i == 0 else order[::-1])))
    return cases, groups


def path_for(out, case, method, repeat=0, attempt=0):
    name = cell_id(case)
    if not repeat:
        return out/'audit'/f'{name}_{method}.json'
    return out/'timing'/f'{name}_r{repeat}_a{attempt}_{method}.json'


def anchored(snapshot, case, preset, expected):
    path = snapshot/'traces'/f'{cell_id(case)}.json'
    ref, _ = reference(snapshot, case, expected)
    require(ref['cfg'] == dict(config(preset, case['seed']), public_size=case['public_size']),
            'Wrong confirmation configuration')
    return ref, path


def worker(opts, out, confirmation, manifest, identity, cases):
    i, method, repeat, attempt = opts.worker
    repeat, attempt = int(repeat), int(attempt)
    case = cases[int(i)]
    cell = cell_id(case)
    ref, _ = anchored(confirmation, case, opts.preset, manifest['traces'][cell])
    snapshot = out/'preparation'/f'{cell}.json'
    bank_path = confirmation/'banks'/f'{case["seed"]}.json'
    prep = sealed(snapshot)
    require(manifest['environment'] == environment() and prep['manifest'] == identity
            and sha(bank_path) == manifest['banks'][str(case['seed'])], 'Worker inputs changed')
    if repeat:
        require(sealed(out/'audited.json')['manifest'] == identity, 'Timing precedes audit')
    args = (confirmation, ref, config(opts.preset, case['seed']), snapshot, sealed(bank_path))
    if method == 'Demand':
        baseline = sealed(path_for(out, case, 'B'))
        require(baseline['manifest'] == identity, 'Missing same-session full B audit')
        result = demand_run(*args, baseline, audit=not repeat)
    else:
        result = full_worker.run(*args, method, audit=not repeat)
    seal(path_for(out, case, method, repeat, attempt),
         dict(manifest=identity, case=case, method=method, repeat=repeat, attempt=attempt, **result))


def execute(opts, out, confirmation):
    cases, groups = schedule(opts.preset)
    marker = out/'manifest.json'
    if opts.worker:
        manifest = read(marker)
        require(manifest['preset'] == opts.preset and manifest['confirmation'] == str(confirmation)
                and manifest['cases'] == cases and manifest['groups'] == groups, 'Worker schedule changed')
        worker(opts, out, confirmation, manifest, sha(marker), cases)
        return
    prior = sealed(confirmation/'completed.json')
    require(prior['manifest'] == sha(confirmation/'manifest.json') and
            read(confirmation/'manifest.json')['preset'] == opts.preset, 'Invalid confirmation input')
    refs, traces, banks = {}, {}, {}
    for case in cases:
        cell = cell_id(case)
        traces[cell] = prior['traces'][cell]
        ref, path = anchored(confirmation, case, opts.preset, traces[cell])
        require(raw_sha(path.with_suffix('.npz')) == ref['payload_sha256'], f'Modified trace {cell}')
        refs[cell] = ref
        seed = str(case['seed'])
        if seed not in banks:
            bank = confirmation/'banks'/f'{seed}.json'
            verify_bank(bank)
            banks[seed] = sha(bank)

    manifest = dict(preset=opts.preset, cases=cases, groups=groups, confirmation=str(confirmation),
                    prior_complete=sha(confirmation/'completed.json'), traces=traces, banks=banks,
                    environment=environment(), dependencies=sources(),
                    package={p.name: sha(p) for p in sorted(PACKAGE.glob('*.py'))},
                    reused={p: sha(PACKAGE.parent/p) for p in ('confirmation/run.py','full_training/worker.py',
                                                               'full_training/run.py','report.py')},
                    design_sha256=sha(PACKAGE/'README.md'), threshold_pct=3., minimum_wins=2)
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical inputs and sources')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Choose a fresh output directory')
        write(marker, manifest)
    identity = sha(marker)
    done_path = out/'completed.json'
    old = sealed(done_path) if receipt(done_path).exists() else None

    def launch(case, method, repeat=0, attempt=0):
        phase = f'block {repeat}, attempt {attempt}' if repeat else 'audit'
        print(f'{cell_id(case)} {method} {phase}', flush=True)
        subprocess.run([sys.executable, '-B', '-m', 'snapshot_routing.on_demand.run',
                        '--preset', opts.preset, '--confirmation', str(confirmation), '--output', str(out),
                        '--worker', str(cases.index(case)), method, str(repeat), str(attempt)], cwd=ROOT, check=True)

    def read_run(case, method, repeat=0, attempt=0):
        path = path_for(out, case, method, repeat, attempt)
        record = sealed(path)
        cfg = refs[cell_id(case)]['cfg']
        require((record['manifest'], record['case'], record['method'], record['repeat'], record['attempt']) ==
                (identity, case, method, repeat, attempt) and len(record['observed']) == cfg['rounds'],
                f'Invalid run {path}')
        if repeat:
            require(len(record['timing']) == cfg['rounds'] and record['comparisons'] == 0,
                    f'Incomplete measurement {path}')
        else:
            expected = (len(cfg['widths'])*sum(r['edges'] for r in record['scope']) if method == 'Demand'
                        else refs[cell_id(case)]['comparisons'])
            require(record['comparisons'] == expected and
                    [e['round'] for e in record['evaluations']] == checkpoints(cfg), f'Incomplete audit {path}')
        return record, path

    audit_data, audit_hashes = {}, {}
    for case in cases:
        cell = cell_id(case)
        prep = out/'preparation'/f'{cell}.json'
        if not receipt(prep).exists():
            require(old is None, 'A completed experiment lost preparation')
            full_worker.prepare_snapshot(confirmation, refs[cell], config(opts.preset, case['seed']), prep, identity)
        prepared = sealed(prep)
        require(prepared['model_sha'] == sha(prep.with_suffix('.pt')) and prepared['manifest'] == identity,
                'Selected snapshot changed')
        audit_hashes[prep.relative_to(out).as_posix()] = sha(prep)
        for method in METHODS:
            if not receipt(path_for(out, case, method)).exists():
                require(old is None, 'A completed experiment lost an audit')
                launch(case, method)
            record, path = read_run(case, method)
            audit_data[cell, method] = record
            b = audit_data[cell, 'B']
            require(record['evaluations'] == b['evaluations'], 'Native quality changed')
            if method == 'Demand':
                require([student_trace(r) for r in record['observed']] ==
                        [student_trace(r) for r in b['observed']], 'Demand changed the student trajectory')
            else:
                require(record['observed'] == b['observed'] and record['traffic'] == b['traffic'],
                        'Full-graph trajectories or bytes differ')
            audit_hashes[path.relative_to(out).as_posix()] = sha(path)
    audit_path = out/'audited.json'
    audit_record = dict(manifest=identity, hashes=audit_hashes)
    if receipt(audit_path).exists():
        require(sealed(audit_path) == audit_record, 'Audit seal changed')
    else:
        require(old is None, 'A completed experiment lost its audit seal')
        seal(audit_path, audit_record)
    runs, blocks = [], {}
    for group in groups:
        case, repeat = group['case'], group['repeat']
        cell = cell_id(case)
        for attempt in (0, 1):
            path = out/'blocks'/f'{cell}_r{repeat}_a{attempt}.json'
            saved = sealed(path) if receipt(path).is_file() else None
            require(saved is not None or old is None, 'A completed experiment lost a timing block')
            subset, hashes = [], {}
            for method in group['order']:
                if saved is None:
                    launch(case, method, repeat, attempt)
                record, run_path = read_run(case, method, repeat, attempt)
                audit = audit_data[cell, method]
                require(record['observed'] == audit['observed'] and record['traffic'] == audit['traffic'],
                        f'Timed training differs from audit: {run_path}')
                if method == 'Demand':
                    require(record['scope'] == audit['scope'] and record['traffic_breakdown'] == audit['traffic_breakdown'],
                            'Timed Demand scope or bytes changed')
                hashes[run_path.relative_to(out).as_posix()] = sha(run_path)
                subset.append(record)
            block = dict(manifest=identity, group=group, attempt=attempt, runs=hashes)
            if saved is None:
                seal(path, block)
            else:
                require(saved == block, 'Timing block changed')
            runs.extend(subset)
            blocks[path.relative_to(out).as_posix()] = sha(path)
            if not any(r['suspend_seconds'] is not None and r['suspend_seconds'] >= 1. for r in subset):
                break
    done = dict(manifest=identity, audit=sha(audit_path), blocks=blocks)
    require(old is None or old == done, 'Completion evidence changed')
    report(out, runs, audit_data, manifest)
    seal(done_path, done)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full','smoke'), default='full')
    parser.add_argument('--confirmation', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=4, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    defaults = ('snapshot_routing_confirmation_full' if opts.preset == 'full'
                else 'snapshot_routing_confirmation_release_smoke')
    source = (opts.confirmation or ROOT/'outputs'/defaults).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_on_demand_{opts.preset}').resolve()
    require(not (out.is_relative_to(source) or source.is_relative_to(out)), 'Output overlaps confirmation input')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, source)


if __name__ == '__main__':
    main()
