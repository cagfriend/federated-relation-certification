"""Diagnose B/D timing with matched same-method controls."""

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
    ROOT, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import verify_bank

from ..confirmation.run import config
from ..full_training.run import reference
from .probe import measure
from .report import report

PACKAGE = Path(__file__).resolve().parent
CASES = ((2021, 'dirichlet_0.1'), (2023, 'dirichlet_0.1'), (2021, 'iid'))
ORDERS = ('BBDD', 'DBBD', 'DDBB', 'BDDB', 'DBBD', 'BBDD', 'BDDB', 'DDBB')


def plan(preset):
    contexts = CASES if preset == 'full' else (CASES[0], CASES[2])
    size = 4096 if preset == 'full' else 64
    cases = [dict(seed=s, partition=p, public_size=size) for s, p in contexts]
    orders = ORDERS if preset == 'full' else ORDERS[:1]
    blocks = []
    for i in range(len(orders)):
        for offset in range(len(cases)):
            j = (offset+i) % len(cases)
            case = cases[j]
            blocks.append(dict(case=case, number=i+1, order=orders[(i+j) % len(orders)]))
    return cases, blocks, len(orders)


def source_records(opts, source, confirmation, cases):
    m = read(source/'manifest.json')
    complete = sealed(source/'completed.json')
    audited = sealed(source/'audited.json')
    require(m['preset'] == opts.preset and complete['manifest'] == audited['manifest'] == sha(source/'manifest.json')
            and complete['audit'] == sha(source/'audited.json'), 'E43 completion or audit receipt changed')
    upstream = sealed(confirmation/'completed.json')
    require(sha(confirmation/'completed.json') == m['upstream_complete'], 'E42 confirmation identity changed')
    records = {}
    for case in cases:
        cell = cell_id(case)
        require(case in m['cases'] and m['references'][cell] == upstream['traces'][cell], 'Wrong E43 context')
        ref, _ = reference(confirmation, case, m['references'][cell])
        require(ref['cfg'] == dict(config(opts.preset, case['seed']), public_size=case['public_size']),
                f'Invalid reference configuration {cell}')
        observed = {}
        for method in 'BD':
            rel = f'audit/{cell}_{method}.json'
            audit = sealed(source/rel)
            require(audited['hashes'][rel] == sha(source/rel) and audit['case'] == case and audit['method'] == method
                    and audit['manifest'] == audited['manifest'] and audit['comparisons'] == ref['comparisons']
                    and len(audit['observed']) == ref['cfg']['rounds'],
                    f'Invalid E43 audit {rel}')
            require(audit['evaluations'] == ref['quality'] and audit['traffic'] == ref['traffic'][-1],
                    'E43 audit differs from E42 quality or traffic')
            if method == 'B':
                observed = audit['observed']
            else:
                require(audit['observed'] == observed, f'E43 B/D trajectory mismatch for {cell}')
        prep = f'preparation/{cell}.json'
        setup = sealed(source/prep)
        require(audited['hashes'][prep] == sha(source/prep) and setup['manifest'] == audited['manifest']
                and setup['model_sha'] == sha((source/prep).with_suffix('.pt')), f'Invalid snapshot {cell}')
        records[cell] = dict(trace=m['references'][cell], preparation=audited['hashes'][prep], observed=observed)
    banks = {str(c['seed']): m['banks'][str(c['seed'])] for c in cases}
    return records, banks


def location(out, block, attempt, position=None):
    stem = f"{cell_id(block['case'])}_r{block['number']}_a{attempt}"
    if position is None:
        return out/'blocks'/f'{stem}.json'
    return out/'timing'/f'{stem}_p{position}_{block["order"][position-1]}.json'


def process_state():
    try:
        import psutil
        process = psutil.Process()
        return dict(cpu_affinity=process.cpu_affinity(), priority=process.nice())
    except (ImportError, OSError, AttributeError):
        return {}
    except psutil.Error:
        return {}


def work(opts, out, source, confirmation, manifest, identity, blocks):
    index, attempt, position = map(int, opts.worker)
    require(0 <= index < len(blocks) and attempt in (0, 1) and 1 <= position <= 4, 'Invalid worker slot')
    block = blocks[index]
    case, method = block['case'], block['order'][position-1]
    cell = cell_id(case)
    ref, _ = reference(confirmation, case, manifest['references'][cell]['trace'])
    snapshot = source/'preparation'/f'{cell}.json'
    bank = confirmation/'banks'/f'{case["seed"]}.json'
    require(manifest['environment'] == environment() and
            sha(bank) == manifest['banks'][str(case['seed'])] and
            sha(snapshot) == manifest['references'][cell]['preparation'], 'Worker inputs changed')
    state = process_state()
    result = measure(confirmation, ref, config(opts.preset, case['seed']), snapshot, sealed(bank), method)
    seal(location(out, block, attempt, position), dict(manifest=identity, cell=cell, block=block['number'],
         attempt=attempt, position=position, method=method, process_state=state, **result))


def execute(opts, out, source, confirmation):
    cases, blocks, n = plan(opts.preset)
    marker = out/'manifest.json'
    if opts.worker:
        manifest = read(marker)
        require(manifest['preset'] == opts.preset and manifest['schedule'] == blocks
                and manifest['source'] == str(source) and manifest['confirmation'] == str(confirmation),
                'Worker configuration differs from schedule')
        work(opts, out, source, confirmation, manifest, sha(marker), blocks)
        return
    records, banks = source_records(opts, source, confirmation, cases)
    for seed, expected in banks.items():
        bank = confirmation/'banks'/f'{seed}.json'
        verify_bank(bank)
        require(sha(bank) == expected, f'Bank receipt changed for seed {seed}')
    references = {cell: {k: v for k, v in payload.items() if k != 'observed'} for cell, payload in records.items()}
    manifest = dict(preset=opts.preset, cells=list(references), schedule=blocks, blocks_per_cell=n,
                    same_direction_per_order=3, head_threshold_pct=3., source=str(source),
                    confirmation=str(confirmation), source_sha256=sha(source/'completed.json'),
                    confirmation_sha256=sha(confirmation/'completed.json'), references=references, banks=banks,
                    environment=environment(), clocks={k: vars(get_clock_info(k)) for k in ('perf_counter','process_time')},
                    dependencies=sources(), package={p.name: sha(p) for p in sorted(PACKAGE.glob('*.py'))},
                    shared={p: sha(PACKAGE.parent/p) for p in ('report.py', 'confirmation/run.py',
                                                               'full_training/run.py', 'full_training/worker.py')},
                    design_sha256=sha(PACKAGE/'README.md'))
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical input, code and environment')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use an empty output directory')
        write(marker, manifest)
    identity = sha(marker)
    completion = out/'completed.json'
    old = sealed(completion) if receipt(completion).exists() else None
    hashes, runs = {}, []
    for index, block in enumerate(blocks):
        cell = cell_id(block['case'])
        for attempt in (0, 1):
            block_path = location(out, block, attempt)
            previous = sealed(block_path) if receipt(block_path).exists() else None
            require(previous is not None or old is None, 'A completed run lost its block receipt')
            group, paths = [], {}
            for position, method in enumerate(block['order'], 1):
                path = location(out, block, attempt, position)
                if previous is None:
                    print(f'{index+1}/{len(blocks)} {cell} order={block["order"]} '
                          f'position={position} {method} attempt={attempt}', flush=True)
                    subprocess.run([sys.executable, '-B', '-m', 'snapshot_routing.timing_diagnosis.run',
                                    '--preset', opts.preset, '--source', str(source), '--confirmation', str(confirmation),
                                    '--output', str(out), '--worker', str(index), str(attempt), str(position)],
                                   cwd=ROOT, check=True)
                result = sealed(path)
                require((result['manifest'], result['cell'], result['block'], result['attempt'],
                         result['position'], result['method']) ==
                        (identity, cell, block['number'], attempt, position, method) and
                        result['observed'] == records[cell]['observed'] and
                        [r['round'] for r in result['rounds']] == list(range(1, len(result['observed'])+1)),
                        f'Invalid timing or changed trajectory: {path}')
                paths[path.relative_to(out).as_posix()] = sha(path)
                group.append(result)
            record = dict(manifest=identity, schedule=block, attempt=attempt, hashes=paths)
            if previous is None:
                seal(block_path, record)
            else:
                require(previous == record, f'Timing block changed: {block_path}')
            hashes[block_path.relative_to(out).as_posix()] = sha(block_path)
            runs.extend(group)
            if not any(r['suspend_seconds'] is not None and r['suspend_seconds'] >= 1. for r in group):
                break
    done = dict(manifest=identity, blocks=hashes)
    require(old is None or old == done, 'Completion evidence changed')
    report(out, runs, manifest)
    seal(completion, done)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full','smoke'), default='full')
    parser.add_argument('--source', type=Path, help='Completed full head experiment (E43)')
    parser.add_argument('--confirmation', type=Path, help='Input data from E42')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=3, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    source = (opts.source or ROOT/'outputs'/f'snapshot_routing_training_{opts.preset}').resolve()
    default_confirmation = read(source/'manifest.json')['source']
    confirmation = (opts.confirmation or Path(default_confirmation)).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_timing_diagnosis_{opts.preset}').resolve()
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (source, confirmation)),
            'Output overlaps source')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, source, confirmation)


if __name__ == '__main__':
    main()
