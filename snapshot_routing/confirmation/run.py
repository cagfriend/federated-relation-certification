"""Confirm the frozen B/D/B rule on independent STL-10 seeds."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

for var in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[var] = '1'

import numpy as np
import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (
    ROOT, TRIPLES, cfg_for, checkpoints, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_graph_scaling.design import SIZES, cell_id
from experiments.snapshot_graph_scaling.inputs import raw_sha

from ..replay import replay
from .capture import capture_seed
from .report import report

PACKAGE = Path(__file__).resolve().parent
SEEDS = (2021, 2022, 2023)
PARTITIONS = ('iid', 'dirichlet_0.1')
DATA_FILES = ('train_X.bin', 'train_y.bin', 'unlabeled_X.bin', 'test_X.bin', 'test_y.bin')


def design(preset):
    sizes = SIZES[preset]
    rule = dict(zip(sizes, 'BDB', strict=True))
    cases, blocks = [], []
    for seed in SEEDS if preset == 'full' else SEEDS[:1]:
        for partition in PARTITIONS:
            cases.extend(dict(seed=seed, partition=partition, public_size=size) for size in sizes)
    reps = 3 if preset == 'full' else 1
    for i, case in enumerate(cases):
        for repeat, order in enumerate(TRIPLES[i % 2][:reps], 1):
            blocks.append(dict(case=case, repeat=repeat, order=order))
    return cases, blocks, rule


def config(preset, seed):
    return dict(cfg_for(preset, seed), partitions=list(PARTITIONS))


def trace_record(out, case, identity, preset):
    cell = cell_id(case)
    path = out/'traces'/f'{cell}.npz'
    record = sealed(path.with_suffix('.json'))
    require(record['manifest'] == identity and record['case'] == case, f'Unexpected trace {cell}')
    if record['status'] == 'initialization_blocked':
        require(record['blocked_clients'] and not path.exists(), f'Unexpected blocked trace {cell}')
    else:
        cfg = dict(config(preset, case['seed']), public_size=case['public_size'])
        require(record['status'] == 'captured' and not record['blocked_clients'] and record['cfg'] == cfg and
                len(record['head_digests']) == len(record['same_edges']) == len(record['traffic']) == cfg['rounds'] and
                [x['round'] for x in record['quality']] == checkpoints(cfg) and
                record['comparisons'] == cfg['rounds']*len(cfg['widths'])*cfg['public_size']//2,
                f'Incomplete teacher trace {cell}')
    return path, record


def job_path(out, block, method):
    return out/'timing'/f"{cell_id(block['case'])}_r{block['repeat']}_{method}.json"


def run_worker(opts, out, cases, blocks, manifest, identity):
    require(manifest['environment'] == environment(), 'Worker environment differs from manifest')
    if opts.capture is not None:
        selected = [c for c in cases if c['seed'] == opts.capture]
        require(selected, 'Unknown capture seed')
        pending = {cell_id(c) for c in selected
                   if not receipt(out/'traces'/f'{cell_id(c)}.json').exists()}
        capture_seed(out, config(opts.preset, opts.capture), selected, opts.data_dir, manifest['raw_data'],
                     identity, pending)
        return
    index, method = opts.replay
    block = blocks[int(index)]
    require(method in block['order'], 'Wrong replay method')
    path, ref = trace_record(out, block['case'], identity, opts.preset)
    require(ref['status'] == 'captured' and raw_sha(path) == ref['payload_sha256'], f'Invalid trace {path}')
    # Give each independent process the same small BLAS warm-up.
    warm = np.ones((32, 32))
    _ = warm @ warm
    with np.load(path, allow_pickle=False) as trace:
        result = replay(method, trace, {}, opts.preset == 'smoke')
    seal(job_path(out, block, method), dict(manifest=identity, trace_sha=ref['payload_sha256'],
         trace_receipt=sha(path.with_suffix('.json')), method=method, cell=cell_id(block['case']),
         case=block['case'], repeat=block['repeat'], **result))


def execute(opts, out):
    cases, blocks, rule = design(opts.preset)
    manifest_path = out/'manifest.json'
    if opts.capture is not None or opts.replay is not None:
        manifest = read(manifest_path)
        require(manifest['preset'] == opts.preset and manifest['cases'] == cases and manifest['schedule'] == blocks
                and manifest['data_dir'] == (str(opts.data_dir) if opts.preset == 'full' else None),
                'Worker configuration differs from manifest')
        run_worker(opts, out, cases, blocks, manifest, sha(manifest_path))
        return

    raw_data = {}
    if opts.preset == 'full':
        print('Checking STL-10 input files ...', flush=True)
        for name in DATA_FILES:
            path = opts.data_dir/name
            require(path.is_file(), f'Missing STL-10 input file: {path}')
            raw_data[name] = raw_sha(path)
    manifest = dict(preset=opts.preset, cases=cases, schedule=blocks, rule={str(k): v for k, v in rule.items()},
                    relative_threshold=.03, min_wins=2, paired_repeats=3 if opts.preset == 'full' else 1,
                    data_dir=str(opts.data_dir) if raw_data else None, raw_data=raw_data,
                    environment=environment(), dependencies=sources(),
                    package={p.relative_to(PACKAGE.parent).as_posix(): sha(p) for p in
                             [*sorted(PACKAGE.glob('*.py')), PACKAGE.parent/'replay.py', PACKAGE.parent/'report.py']},
                    design_sha=sha(PACKAGE/'README.md'))
    if manifest_path.exists():
        require(opts.resume and read(manifest_path) == manifest, 'Resume requires identical inputs and code')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a new output directory')
        write(manifest_path, manifest)
    identity = sha(manifest_path)
    done_path = out/'completed.json'
    old = sealed(done_path) if receipt(done_path).exists() else None

    def launch(*argv):
        subprocess.run([sys.executable, '-B', '-m', 'snapshot_routing.confirmation.run', '--preset', opts.preset,
                        '--output', str(out), '--data-dir', str(opts.data_dir), *argv], cwd=ROOT, check=True)

    for seed in sorted({c['seed'] for c in cases}):
        if any(not receipt(out/'traces'/f'{cell_id(c)}.json').exists() for c in cases if c['seed'] == seed):
            require(old is None, 'Completed run lost a trace receipt')
            print(f'Preparing independent seed {seed}', flush=True)
            launch('--capture', str(seed))
    traces, trace_shas = {}, {}
    for case in cases:
        cell = cell_id(case)
        path, ref = trace_record(out, case, identity, opts.preset)
        if ref['status'] == 'captured':
            require(raw_sha(path) == ref['payload_sha256'], f'Modified trace {cell}')
        traces[cell] = ref
        trace_shas[cell] = sha(path.with_suffix('.json'))
    if old is not None:
        require(old['manifest'] == identity and old['traces'] == trace_shas, 'Completed traces changed')

    data, hashes, block_hashes = [], {}, {}
    for index, block in enumerate(blocks):
        cell = cell_id(block['case'])
        ref = traces[cell]
        if ref['status'] != 'captured':
            continue
        block_path = out/'blocks'/f'{cell}_r{block["repeat"]}.json'
        previous_block = sealed(block_path) if receipt(block_path).exists() else None
        if previous_block is None:
            require(old is None, 'Completed run lost a block receipt')
        block_runs = {}
        for method in block['order']:
            path = job_path(out, block, method)
            relative = path.relative_to(out).as_posix()
            if previous_block is None:
                # A partial block may straddle interruption or a machine-state change.
                print(f'Block {index+1}/{len(blocks)} {cell} r{block["repeat"]} {method}', flush=True)
                launch('--replay', str(index), method)
            run = sealed(path)
            require((run['manifest'], run['cell'], run['case'], run['repeat'], run['method'],
                     run['trace_sha'], run['trace_receipt'])
                    == (identity, cell, block['case'], block['repeat'], method, ref['payload_sha256'], trace_shas[cell]) and
                    len(run['rows']) == ref['cfg']['rounds'] and run['comparisons'] == ref['comparisons'] and
                    all(row['routes'] == [method]*len(ref['cfg']['widths']) for row in run['rows']),
                    f'Incomplete or mismatched replay: {path}')
            block_runs[relative] = sha(path)
            data.append(run)
        block_record = dict(manifest=identity, block=block, runs=block_runs)
        if previous_block is None:
            seal(block_path, block_record)
        else:
            require(previous_block == block_record, f'Paired block changed: {block_path}')
        hashes.update(block_runs)
        block_hashes[block_path.relative_to(out).as_posix()] = sha(block_path)
    completion = dict(manifest=identity, traces=trace_shas, runs=hashes, blocks=block_hashes)
    require(old is None or old == completion, 'Completed records changed')
    report(out, cases, traces, data, rule, manifest)
    seal(done_path, completion)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'experiments/stl10_transfer/data/stl10_binary')
    parser.add_argument('--resume', action='store_true')
    worker = parser.add_mutually_exclusive_group()
    worker.add_argument('--capture', type=int, help=argparse.SUPPRESS)
    worker.add_argument('--replay', nargs=2, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    opts.data_dir = opts.data_dir.resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_confirmation_{opts.preset}').resolve()
    require(not (out.is_relative_to(opts.data_dir) or opts.data_dir.is_relative_to(out)), 'Output overlaps dataset')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out)


if __name__ == '__main__':
    main()
