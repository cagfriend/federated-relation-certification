"""Audit incremental certificates and join them to the independent E42 timings."""

import argparse
import os
from pathlib import Path

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import numpy as np
import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import ROOT, environment, read, receipt, require, seal, sealed, sha, write
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import raw_sha

from ..confirmation.run import design, job_path, trace_record
from .replay import replay
from .report import build

PACKAGE = Path(__file__).resolve().parent


def original(source, preset):
    cases, blocks, rule = design(preset)
    marker = source/'manifest.json'
    m = read(marker)
    done = sealed(source/'completed.json')
    identity = sha(marker)
    require(m['preset'] == preset and m['cases'] == cases and m['schedule'] == blocks and
            m['rule'] == {str(k): v for k, v in rule.items()} and done['manifest'] == identity,
            'Expected the complete E42 confirmation schedule')
    return cases, blocks, done, identity


def timing_records(source, blocks, done, identity):
    result = {cell_id(b['case']): [] for b in blocks}
    for group in blocks:
        case, repeat = group['case'], group['repeat']
        cell = cell_id(case)
        path = source/'blocks'/f'{cell}_r{repeat}.json'
        sealed_group = sealed(path)
        require(sha(path) == done['blocks'][path.relative_to(source).as_posix()] and
                sealed_group['manifest'] == identity and sealed_group['block'] == group, 'E42 timing block changed')
        methods = {}
        for method in group['order']:
            timed = job_path(source, group, method)
            record = sealed(timed)
            key = timed.relative_to(source).as_posix()
            require(sha(timed) == sealed_group['runs'][key] == done['runs'][key] and
                    (record['case'], record['method'], record['repeat'], record['manifest']) ==
                    (case, method, repeat, identity), 'E42 timing record changed')
            methods[method] = record
        result[cell].append(methods)
    return result


def verify_replay(result, ref, groups):
    rows = result['rows']
    cfg = ref['cfg']
    require([row['round'] for row in rows] == list(range(1, cfg['rounds']+1)) and
            all(len(row['clients']) == len(cfg['widths']) for row in rows) and
            result['comparisons'] == 2*ref['comparisons'], 'Incomplete E/D replay')
    expected = {'B': [[cfg['public_size']]*len(cfg['widths']) for _ in rows]}
    for method in ('E','D'):
        expected[method] = [[c[f'{method.lower()}_forward'] for c in row['clients']] for row in rows]
    for group in groups:
        for method, record in group.items():
            require(record['trace_sha'] == ref['payload_sha256'] and record['comparisons'] == ref['comparisons']
                    and record['probe_comparisons'] == 0 and
                    [x['endpoints'] for x in record['rows']] == expected[method],
                    'Replayed endpoint counts differ from a sealed E42 timing run')
            require(record['peak_cache_bytes'] == result['cache_bytes'].get(method, 0),
                    'Cache size differs from E42')


def execute(source, out, preset, resume):
    cases, blocks, reference, original_id = original(source, preset)
    times = timing_records(source, blocks, reference, original_id)
    inputs = {}
    for case in cases:
        cell = cell_id(case)
        path, ref = trace_record(source, case, original_id, preset)
        header = path.with_suffix('.json')
        require(ref['status'] == 'captured' and sha(header) == reference['traces'][cell] and
                raw_sha(path) == ref['payload_sha256'], f'Missing or changed teacher trace {cell}')
        inputs[cell] = (path, ref)
        require(all(r['trace_receipt'] == reference['traces'][cell] for b in times[cell] for r in b.values()),
                f'E42 timing uses a different trace receipt for {cell}')
    package_inputs = [*sorted(PACKAGE.glob('*.py')), PACKAGE.parent/'confirmation/run.py',
                      PACKAGE.parent/'replay.py', PACKAGE.parent/'report.py',
                      ROOT/'experiments/public_scaling/certification.py']
    manifest = dict(preset=preset, source=str(source), reference=sha(source/'completed.json'),
                    cases=cases, environment=environment(), traces=reference['traces'],
                    package={p.relative_to(ROOT).as_posix(): sha(p) for p in package_inputs},
                    design_sha256=sha(PACKAGE/'README.md'))
    marker = out/'manifest.json'
    if marker.exists():
        require(resume and read(marker) == manifest, 'Resume requires the same input and analysis code')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a new output directory')
        write(marker, manifest)
    identity = sha(marker)
    completed = out/'completed.json'
    old = sealed(completed) if receipt(completed).exists() else None
    analyzed, hashes = {}, {}
    for i, case in enumerate(cases, 1):
        cell = cell_id(case)
        source_path, ref = inputs[cell]
        path = out/'cells'/f'{cell}.json'
        if not receipt(path).is_file():
            require(old is None, 'A completed analysis lost a cell')
            print(f'{i}/{len(cases)} {cell} replaying independent E/D caches', flush=True)
            with np.load(source_path, allow_pickle=False) as trace:
                result = replay(trace, ref['cfg'])
            verify_replay(result, ref, times[cell])
            seal(path, dict(manifest=identity, case=case, trace_sha=ref['payload_sha256'], **result))
        result = sealed(path)
        require((result['manifest'], result['case'], result['trace_sha']) ==
                (identity, case, ref['payload_sha256']), 'Unexpected mechanism replay result')
        verify_replay(result, ref, times[cell])
        analyzed[cell] = result
        hashes[path.relative_to(out).as_posix()] = sha(path)
    done = dict(manifest=identity, cells=hashes)
    require(old is None or old == done, 'Previously analyzed data changed')
    build(out, cases, analyzed, times, preset)
    seal(completed, done)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full','smoke'), default='full')
    parser.add_argument('--source', type=Path, help='Completed local E42 confirmation')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    opts = parser.parse_args()
    name = ('snapshot_routing_confirmation_full' if opts.preset == 'full'
            else 'snapshot_routing_confirmation_release_smoke')
    source = (opts.source or ROOT/'outputs'/name).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_mechanism_{opts.preset}').resolve()
    require(not (out.is_relative_to(source) or source.is_relative_to(out)), 'Output overlaps E42')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(source, out, opts.preset, opts.resume)


if __name__ == '__main__':
    main()
