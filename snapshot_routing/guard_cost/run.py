"""Run the four-way ablation on frozen STL-10 teacher traces."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (
    ROOT, environment, read, receipt, require, seal, sealed, sha, write,
)
from experiments.snapshot_graph_scaling.inputs import raw_sha
from ..bias_resources.worker import non_timing
from ..numerical_boundary.replay import references
from .report import report
from .worker import METHODS, eligible, replay

MODULE = 'snapshot_routing.guard_cost.run'
PACKAGE = Path(__file__).resolve().parent
ORDERS = ('DWCS', 'WSDC', 'SCWD', 'CDSW')
SHARED = ('bias_resources/worker.py', 'numerical_boundary/guard.py', 'numerical_boundary/replay.py',
          'confirmation/run.py', 'report.py')


def design(entries, preset):
    rounds = 200 if preset == 'full' else 10
    traces = {}
    for cell, path, ref in entries:
        if preset == 'smoke' and traces:
            break
        require(ref['cfg']['rounds'] == 200 and ref['cfg']['public_size'] == 4096, f'Unexpected trace configuration {cell}')
        traces[cell] = dict(path=str(path), metadata=sha(path.with_suffix('.json')), sha=ref['payload_sha256'],
                            case=ref['case'], rounds=rounds,
                            comparisons=ref['comparisons']*rounds//ref['cfg']['rounds'])
    require(len(traces) == (4 if preset == 'full' else 1), 'Incomplete source matrix')
    cells = list(traces)
    blocks = [dict(cell=cells[(i + rep) % len(cells)], repeat=rep+1,
                   order=ORDERS[(i + 2*rep) % len(ORDERS)] if preset == 'full' else ORDERS[0])
              for rep in range(4 if preset == 'full' else 1) for i in range(len(cells))]
    profiles = [dict(cell=cell, repeat=0, order=ORDERS[(2*i+1) % len(ORDERS)]) for i, cell in enumerate(cells)]
    return traces, blocks + profiles


def path_for(out, block, attempt, method=None):
    stem = f"{block['cell']}_r{block['repeat']}_a{attempt}"
    if method is None:
        return out/'blocks'/f'{stem}.json'
    return out/('runs' if block['repeat'] else 'profile')/f'{stem}_{method}.json'


def signature(run):
    return non_timing(run), run['scale_fallbacks'], run['rebuilds']


def work(out, args):
    index, attempt, method = args
    index, attempt = int(index), int(attempt)
    marker = out/'manifest.json'
    manifest = read(marker)
    require(manifest['environment'] == environment(), 'Worker environment differs')
    require(method in METHODS and 0 <= index < len(manifest['schedule']) and attempt in (0, 1), 'Invalid slot')
    block = manifest['schedule'][index]
    trace = manifest['traces'][block['cell']]
    path = Path(trace['path'])
    metadata = path.with_suffix('.json')
    require(sha(metadata) == trace['metadata'] and raw_sha(path) == trace['sha'], 'Trace changed')
    cfg = sealed(metadata)['cfg']
    result = replay(path, cfg, trace['rounds'], method, profile=block['repeat'] == 0)
    seal(path_for(out, block, attempt, method),
         dict(manifest=sha(marker), **block, attempt=attempt, method=method, **result))


def execute(out, source, preset, resume):
    traces, schedule = design(references(source), preset)
    files = [*PACKAGE.glob('*.py'), PACKAGE/'README.md', *(PACKAGE.parent/path for path in SHARED),
             ROOT/'experiments/public_scaling/certification.py', ROOT/'experiments/public_scaling/endpoint_bias.py',
             ROOT/'experiments/snapshot_certification_timing/worker.py']
    manifest = dict(preset=preset, source=str(source), source_completion=sha(source/'completed.json'),
                    traces=traces, schedule=schedule, environment=environment(),
                    sources={file.relative_to(ROOT).as_posix(): sha(file) for file in sorted(files)})
    marker = out/'manifest.json'
    if marker.is_file():
        require(resume and read(marker) == manifest, 'Resume requires identical trace, code and runtime')
    else:
        require(not out.exists() or (out.is_dir() and not any(out.iterdir())), 'Use an empty output directory')
        write(marker, manifest)
    identity = sha(marker)
    completion_path = out/'completed.json'
    completed = sealed(completion_path) if receipt(completion_path).is_file() else None
    blocks, hashes, signatures = [], {}, {}
    for index, block in enumerate(schedule):
        entry = traces[block['cell']]
        for attempt in (0, 1):
            path = path_for(out, block, attempt)
            previous = sealed(path) if receipt(path).is_file() else None
            require(previous is not None or completed is None, 'Completed experiment lost a replay block')
            group, runs = {}, {}
            for method in block['order']:
                result_path = path_for(out, block, attempt, method)
                if previous is None:
                    print(f"{index+1}/{len(schedule)} {block['cell']} r{block['repeat']} a{attempt} {method}", flush=True)
                    subprocess.run([sys.executable, '-B', '-m', MODULE, '--output', str(out), '--worker',
                                    str(index), str(attempt), method], cwd=ROOT, check=True)
                result = sealed(result_path)
                require(result['manifest'] == identity and result['method'] == method and result['attempt'] == attempt
                        and all(result[key] == val for key, val in block.items())
                        and result['edge_comparisons'] == entry['comparisons']
                        and [row['round'] for row in result['rows']] == list(range(1, entry['rounds']+1))
                        and ('phases' in result) == (block['repeat'] == 0), f'Invalid replay {result_path}')
                key = block['cell'], method
                check = signature(result)
                require(signatures.setdefault(key, check) == check, f'Inconsistent replay trajectory: {result_path}')
                group[method] = result
                runs[method] = sha(result_path)
            paired = dict(manifest=identity, **block, attempt=attempt, runs=runs,
                          eligible=preset == 'smoke' or all(eligible(run) for run in group.values()))
            if previous is None:
                seal(path, paired)
            else:
                require(previous == paired, f'Changed replay block: {path}')
            hashes[path.relative_to(out).as_posix()] = sha(path)
            blocks.append((paired, group))
            slept = any((run['suspend_seconds'] or 0.) >= 1 for run in group.values())
            if preset != 'full' or not slept:
                break
    paths = report(out, manifest, blocks)
    result = dict(manifest=identity, blocks=hashes, reports={path.name: sha(path) for path in paths})
    require(completed is None or completed == result, 'Completion evidence changed')
    seal(completion_path, result)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--source', type=Path, default=ROOT/'outputs/snapshot_routing_confirmation_full')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=3, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_guard_cost_{opts.preset}').resolve()
    source = opts.source.resolve()
    require(not (out.is_relative_to(source) or source.is_relative_to(out)), 'Output overlaps trace source')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        if opts.worker:
            work(out, opts.worker)
        else:
            execute(out, source, opts.preset, opts.resume)


if __name__ == '__main__':
    main()
