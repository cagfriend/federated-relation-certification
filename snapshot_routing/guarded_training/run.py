"""Compare current D and the combined numerical guard in live STL-10 training."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (
    ROOT, checkpoints, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import verify_bank

from ..confirmation.run import config
from ..endpoint_bias_training.run import plan as original_plan
from ..full_training.run import reference
from ..report import eligible
from ..timing_diagnosis.run import source_records
from .report import report
from .worker import train

PACKAGE = Path(__file__).resolve().parent
MODULE = 'snapshot_routing.guarded_training.run'
DEPENDENCIES = ('confirmation/run.py', 'endpoint_bias_training/run.py', 'full_training/run.py',
                'full_training/worker.py', 'timing_diagnosis/run.py', 'numerical_boundary/guard.py', 'report.py')


def plan(preset):
    upstream, cases, blocks = original_plan(preset)
    return upstream, cases, [dict(block, order=block['order'].translate(str.maketrans('BD', 'DC')))
                              for block in blocks]


def path_for(out, block, attempt, method=None):
    stem = f"{block['cell']}_r{block['repeat']}_a{attempt}"
    return out/'pairs'/f'{stem}.json' if method is None else out/'runs'/f'{stem}_{method}.json'


def work(opts, out, source, confirmation, marker):
    manifest = read(marker)
    identity = sha(marker)
    require((manifest['preset'], manifest['source'], manifest['confirmation'], manifest['environment']) ==
            (opts.preset, str(source), str(confirmation), environment()), 'Worker inputs differ from manifest')
    index, attempt, method = opts.worker
    index, attempt = int(index), int(attempt)
    require(0 <= index < len(manifest['schedule']) and attempt in (0, 1), 'Invalid worker slot')
    block = manifest['schedule'][index]
    require(method in block['order'], 'Invalid method for pair')
    cell = block['cell']
    entry = manifest['references'][cell]
    case = entry['case']
    ref, _ = reference(confirmation, case, entry['trace'])
    snapshot = source/'preparation'/f'{cell}.json'
    bank = confirmation/'banks'/f"{case['seed']}.json"
    require(sha(snapshot) == entry['preparation'] and sha(bank) == manifest['banks'][str(case['seed'])],
            f'Input preparation changed for {cell}')
    result = train(confirmation, ref, config(manifest['upstream'], case['seed']), snapshot, sealed(bank),
                   method, entry['rounds'])
    seal(path_for(out, block, attempt, method),
         dict(manifest=identity, **block, attempt=attempt, method=method, **result))


def execute(opts, out, source, confirmation):
    marker = out/'manifest.json'
    if opts.worker:
        work(opts, out, source, confirmation, marker)
        return
    upstream, cases, blocks = plan(opts.preset)
    archived, banks = source_records(argparse.Namespace(preset=upstream), source, confirmation, cases)
    for seed, expected in banks.items():
        bank = confirmation/'banks'/f'{seed}.json'
        verify_bank(bank)
        require(sha(bank) == expected, f'Bank changed for seed {seed}')
    inputs = {}
    for case in cases:
        cell = cell_id(case)
        entry = archived[cell]
        ref, _ = reference(confirmation, case, entry['trace'])
        cfg = ref['cfg']
        require(opts.preset != 'full' or cfg['rounds'] == 200, f'Unexpected full run length for {cell}')
        rounds = 10 if opts.preset == 'real-smoke' else cfg['rounds']
        evaluations = sorted({rnd for rnd in checkpoints(cfg) if rnd <= rounds} | {rounds})
        inputs[cell] = dict(case=case, trace=entry['trace'], preparation=entry['preparation'],
                            rounds=rounds, checkpoints=evaluations, clients=len(cfg['widths']))
    manifest = dict(preset=opts.preset, upstream=upstream, source=str(source), confirmation=str(confirmation),
                    schedule=blocks, references=inputs, banks=banks, environment=environment(),
                    source_completion=sha(source/'completed.json'), trace_completion=sha(confirmation/'completed.json'),
                    dependencies=sources(), shared={name: sha(PACKAGE.parent/name) for name in DEPENDENCIES},
                    package={path.name: sha(path) for path in sorted(PACKAGE.iterdir()) if path.is_file()})
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical source, code and environment')
    else:
        require(not out.exists() or (out.is_dir() and not any(out.iterdir())), 'Use an empty output directory')
        write(marker, manifest)
    identity = sha(marker)
    completed_path = out/'completed.json'
    completed = sealed(completed_path) if receipt(completed_path).is_file() else None
    pairs, hashes = [], {}
    for index, block in enumerate(blocks):
        entry = inputs[block['cell']]
        for attempt in (0, 1):
            pair_path = path_for(out, block, attempt)
            prior = sealed(pair_path) if receipt(pair_path).is_file() else None
            require(prior is not None or completed is None, 'Completed experiment lost a pair')
            run_hashes, process_seconds, group = {}, {}, {}
            for method in block['order']:
                path = path_for(out, block, attempt, method)
                if prior is None:
                    print(f"{index+1}/{len(blocks)} {block['cell']} {block['order']} {method} a{attempt}", flush=True)
                    started = perf_counter()
                    subprocess.run([sys.executable, '-B', '-m', MODULE, '--preset', opts.preset,
                                    '--source', str(source), '--confirmation', str(confirmation), '--output', str(out),
                                    '--worker', str(index), str(attempt), method], cwd=ROOT, check=True)
                    process_seconds[method] = perf_counter() - started
                else:
                    process_seconds[method] = prior['process_seconds'][method]
                run = sealed(path)
                require(run['manifest'] == identity and run['attempt'] == attempt and run['method'] == method
                        and all(run[key] == value for key, value in block.items())
                        and [r['round'] for r in run['rows']] == list(range(1, entry['rounds']+1))
                        and [q['round'] for q in run['quality']] == entry['checkpoints']
                        and all([client['client'] for client in q['clients']] == list(range(entry['clients']))
                                for q in run['quality']), f'Invalid run record: {path}')
                group[method] = run
                run_hashes[method] = sha(path)
            pair = dict(manifest=identity, **block, attempt=attempt, runs=run_hashes, process_seconds=process_seconds,
                        eligible=eligible(group, 'full' if opts.preset == 'full' else 'smoke'))
            if prior is None:
                seal(pair_path, pair)
            else:
                require(prior == pair, f'Pair changed: {pair_path}')
            hashes[pair_path.relative_to(out).as_posix()] = sha(pair_path)
            pairs.append((pair, group))
            slept = any((run['suspend_seconds'] or 0) >= 1 for run in group.values())
            if opts.preset != 'full' or not slept:
                break
    output = report(out, manifest, pairs)
    final = dict(manifest=identity, pairs=hashes, reports={path.name: sha(path) for path in output})
    require(completed is None or completed == final, 'Completion evidence changed')
    seal(completed_path, final)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke', 'real-smoke'), default='full')
    parser.add_argument('--source', type=Path, help='Completed E43 run with selected model snapshots')
    parser.add_argument('--confirmation', type=Path, help='Matching E42 caches')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=3, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    upstream = 'smoke' if opts.preset == 'smoke' else 'full'
    source = (opts.source or ROOT/'outputs'/f'snapshot_routing_training_{upstream}').resolve()
    confirmation = (opts.confirmation or Path(read(source/'manifest.json')['source'])).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_guarded_training_{opts.preset}').resolve()
    require(not any(out.is_relative_to(path) or path.is_relative_to(out) for path in (source, confirmation)),
            'Output overlaps an input directory')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, source, confirmation)


if __name__ == '__main__':
    main()
