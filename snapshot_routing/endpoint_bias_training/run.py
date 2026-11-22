"""Audit and time current D against full B on matched live training."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from time import get_clock_info

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (
    ROOT, checkpoints, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import raw_sha, verify_bank

from ..confirmation.run import config
from ..full_training.run import reference
from ..full_training.worker import run as audit_training
from ..report import eligible
from ..timing_diagnosis.probe import measure
from ..timing_diagnosis.run import process_state, source_records
from .report import report

PACKAGE = Path(__file__).resolve().parent
MODULE = 'snapshot_routing.endpoint_bias_training.run'
SHARED = ('confirmation/run.py', 'full_training/run.py', 'full_training/worker.py', 'full_training/report.py',
          'timing_diagnosis/run.py', 'timing_diagnosis/probe.py', 'report.py')


def plan(preset):
    upstream = 'smoke' if preset == 'smoke' else 'full'
    seeds = (2021,) if upstream == 'smoke' else (2022, 2023)
    size = 64 if upstream == 'smoke' else 4096
    cases = [dict(seed=seed, partition=partition, public_size=size)
             for seed in seeds for partition in ('iid', 'dirichlet_0.1')]
    repeats = 4 if preset == 'full' else 1
    blocks = []
    for repeat in range(repeats):
        for offset in range(len(cases)):
            index = (offset + repeat) % len(cases)
            order = 'BD' if (repeat + index) % 2 == 0 else 'DB'
            blocks.append(dict(cell=cell_id(cases[index]), repeat=repeat + 1, order=order))
    return upstream, cases, blocks


def run_path(out, block, attempt, method=None):
    stem = f"{block['cell']}_r{block['repeat']}_a{attempt}"
    if method is None:
        return out / 'blocks' / f'{stem}.json'
    return out / 'timing' / f'{stem}_{method}.json'


def audit_path(out, cell):
    return out / 'audit' / f'{cell}_D.json'


def work(opts, out, source, confirmation, marker):
    manifest = read(marker)
    identity = sha(marker)
    require((manifest['preset'], manifest['source'], manifest['confirmation'], manifest['environment']) ==
            (opts.preset, str(source), str(confirmation), environment()), 'Worker inputs differ from manifest')
    stage, index, attempt, method = opts.worker
    index, attempt = int(index), int(attempt)
    if stage == 'audit':
        require(0 <= index < len(manifest['cases']) and (attempt, method) == (0, 'D'), 'Invalid audit slot')
        case = manifest['cases'][index]
        path = audit_path(out, cell_id(case))
        slot = dict(stage=stage, attempt=attempt, method=method)
    else:
        require(stage == 'timing' and 0 <= index < len(manifest['schedule']) and attempt in (0, 1),
                'Invalid timing slot')
        block = manifest['schedule'][index]
        require(method in block['order'], 'Invalid timing method')
        case = next(case for case in manifest['cases'] if cell_id(case) == block['cell'])
        path = run_path(out, block, attempt, method)
        slot = dict(stage=stage, attempt=attempt, method=method, repeat=block['repeat'],
                    position=1 + block['order'].index(method))
        require(sealed(out/'audited.json')['manifest'] == identity, 'Timing requires a verified audit')
    cell = cell_id(case)
    entry = manifest['references'][cell]
    ref, _ = reference(confirmation, case, entry['trace'])
    snapshot = source/'preparation'/f'{cell}.json'
    bank_path = confirmation/'banks'/f"{case['seed']}.json"
    require(sha(snapshot) == entry['preparation'] and sha(bank_path) == manifest['banks'][str(case['seed'])],
            f'Input preparation changed for {cell}')
    args = confirmation, ref, config(manifest['upstream_preset'], case['seed']), snapshot, sealed(bank_path), method
    prefix = manifest['prefix']
    if stage == 'audit':
        result = audit_training(*args, audit=True, prefix=prefix)
    else:
        result = measure(*args, prefix=prefix)
        result['process_state'] = process_state()
    seal(path, dict(manifest=identity, cell=cell, **slot, **result))


def equivalent(record, expected):
    fields = ('relations', 'counts', 'targets', 'orders', 'teacher', 'head', 'private_losses', 'public_losses')
    require(len(record['observed']) == len(expected), f"Incomplete trajectory for {record['cell']}")
    for rnd, (actual, anchor) in enumerate(zip(record['observed'], expected, strict=True), 1):
        different = [field for field in fields if actual[field] != anchor[field]]
        require(not different, f"{record['cell']} {record['method']} round {rnd}: {', '.join(different)}")


def execute(opts, out, source, confirmation):
    marker = out/'manifest.json'
    if opts.worker:
        work(opts, out, source, confirmation, marker)
        return
    upstream, cases, blocks = plan(opts.preset)
    records, banks = source_records(argparse.Namespace(preset=upstream), source, confirmation, cases)
    for seed, expected in banks.items():
        bank = confirmation/'banks'/f'{seed}.json'
        verify_bank(bank)
        require(sha(bank) == expected, f'Bank receipt changed for seed {seed}')
    prefix = 10 if opts.preset == 'real-smoke' else None
    references = {}
    for case in cases:
        cell = cell_id(case)
        entry = records[cell]
        ref, path = reference(confirmation, case, entry['trace'])
        require(raw_sha(path.with_suffix('.npz')) == ref['payload_sha256'], f'Invalid E42 trace payload: {cell}')
        rounds = prefix or ref['cfg']['rounds']
        require(rounds in checkpoints(ref['cfg']), 'Run must end at a quality checkpoint')
        entry['observed'] = entry['observed'][:rounds]
        entry['comparisons'] = rounds * len(ref['cfg']['widths']) * (case['public_size']//2)
        entry['traffic'] = ref['traffic'][rounds-1]
        entry['evaluations'] = [row for row in ref['quality'] if row['round'] <= rounds]
        references[cell] = {key: entry[key] for key in ('trace', 'preparation')}
    manifest = dict(preset=opts.preset, upstream_preset=upstream, prefix=prefix, cases=cases, schedule=blocks,
                    source=str(source), confirmation=str(confirmation), banks=banks, references=references,
                    source_sha256=sha(source/'completed.json'), confirmation_sha256=sha(confirmation/'completed.json'),
                    environment=environment(), dependencies=sources(),
                    clocks={k: vars(get_clock_info(k)) for k in ('perf_counter', 'process_time')},
                    package={p.name: sha(p) for p in sorted(PACKAGE.glob('*.py'))},
                    shared={path: sha(PACKAGE.parent/path) for path in SHARED}, design_sha256=sha(PACKAGE/'README.md'),
                    head_threshold_pct=3., min_wins=3)
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical source, code and environment')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use an empty output directory')
        write(marker, manifest)
    identity = sha(marker)
    done = out/'completed.json'
    completed = sealed(done) if receipt(done).is_file() else None

    def invoke(stage, index, attempt, method):
        subprocess.run([sys.executable, '-B', '-m', MODULE, '--preset', opts.preset, '--source', str(source),
                        '--confirmation', str(confirmation), '--output', str(out), '--worker',
                        stage, str(index), str(attempt), method], cwd=ROOT, check=True)

    audits, audit_hashes = [], {}
    for index, case in enumerate(cases):
        cell = cell_id(case)
        path = audit_path(out, cell)
        anchor = records[cell]
        if not receipt(path).is_file():
            require(completed is None, 'Completed experiment lost a D audit')
            print(f'Audit {cell} D', flush=True)
            invoke('audit', index, 0, 'D')
        run = sealed(path)
        require((run['manifest'], run['cell'], run['method'], run['stage'], run['attempt']) ==
                (identity, cell, 'D', 'audit', 0) and run['comparisons'] == anchor['comparisons'] and
                run['evaluations'] == anchor['evaluations'] and run['traffic'] == anchor['traffic'],
                f'Invalid D audit: {path}')
        equivalent(run, anchor['observed'])
        audits.append(run)
        audit_hashes[cell] = sha(path)
    audit_marker = out/'audited.json'
    audit_record = dict(manifest=identity, hashes=audit_hashes)
    if receipt(audit_marker).is_file():
        require(sealed(audit_marker) == audit_record, 'Audit evidence changed')
    else:
        require(completed is None, 'Completed experiment lost the audit receipt')
        seal(audit_marker, audit_record)

    pairs, hashes = [], {}
    for index, block in enumerate(blocks):
        cell = block['cell']
        anchor = records[cell]
        for attempt in (0, 1):
            path = run_path(out, block, attempt)
            previous = sealed(path) if receipt(path).is_file() else None
            require(previous is not None or completed is None, 'Completed experiment lost a timing pair')
            group, paths = {}, {}
            for position, method in enumerate(block['order'], 1):
                if previous is None:
                    print(f"{index+1}/{len(blocks)} {cell} {block['order']} p{position} {method} a{attempt}", flush=True)
                    invoke('timing', index, attempt, method)
                result_path = run_path(out, block, attempt, method)
                run = sealed(result_path)
                require((run['manifest'], run['cell'], run['stage'], run['repeat'], run['attempt'],
                         run['position'], run['method']) ==
                        (identity, cell, 'timing', block['repeat'], attempt, position, method) and
                        run['traffic'] == anchor['traffic'] and
                        [row['round'] for row in run['rounds']] == list(range(1, len(anchor['observed']) + 1)),
                        f'Invalid timing record: {result_path}')
                equivalent(run, anchor['observed'])
                group[method] = run
                paths[method] = sha(result_path)
            pair = dict(manifest=identity, **block, attempt=attempt, runs=paths)
            if previous is None:
                seal(path, pair)
            else:
                require(previous == pair, f'Matched pair changed: {path}')
            hashes[path.relative_to(out).as_posix()] = sha(path)
            clean = eligible(group, opts.preset)
            pairs.append((pair, group, clean))
            slept = any((run['suspend_seconds'] or 0.) >= 1. for run in group.values())
            if opts.preset != 'full' or not slept:
                break
    final = dict(manifest=identity, audit=sha(audit_marker), blocks=hashes)
    require(completed is None or completed == final, 'Completion evidence changed')
    report(out, manifest, pairs, audits)
    seal(done, final)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke', 'real-smoke'), default='full')
    parser.add_argument('--source', type=Path, help='Completed E43 run and selected snapshots')
    parser.add_argument('--confirmation', type=Path, help='Matching E42 traces and feature preparation')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=4, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    upstream = 'smoke' if opts.preset == 'smoke' else 'full'
    source = (opts.source or ROOT/'outputs'/f'snapshot_routing_training_{upstream}').resolve()
    confirmation = (opts.confirmation or Path(read(source/'manifest.json')['source'])).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_endpoint_bias_training_{opts.preset}').resolve()
    require(not any(out.is_relative_to(path) or path.is_relative_to(out) for path in (source, confirmation)),
            'Output overlaps an input directory')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, source, confirmation)


if __name__ == '__main__':
    main()
