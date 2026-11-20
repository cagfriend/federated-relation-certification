"""Audit and time complete M=4096 training on confirmed STL-10 trajectories."""

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
    ROOT, checkpoints, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import raw_sha, verify_bank

from ..confirmation.run import config, design
from .report import report
from .worker import prepare_snapshot, run

PACKAGE = Path(__file__).resolve().parent
METHODS = 'BED'


def upstream(source, preset):
    manifest = read(source/'manifest.json')
    complete = sealed(source/'completed.json')
    identity = sha(source/'manifest.json')
    cases, blocks, _ = design(preset)
    require(manifest['preset'] == preset and manifest['cases'] == cases and manifest['schedule'] == blocks
            and complete['manifest'] == identity, 'Invalid independent confirmation input')
    size = 4096 if preset == 'full' else 64
    cases = [c for c in cases if c['public_size'] == size]
    blocks = [b for b in blocks if b['case']['public_size'] == size]
    return cases, blocks, complete['traces']


def reference(source, case, expected):
    path = source/'traces'/f'{cell_id(case)}.json'
    ref = sealed(path)
    cfg = ref.get('cfg')
    require(sha(path) == expected and ref['case'] == case and ref['status'] == 'captured' and
            cfg['public_size'] == case['public_size'], 'Missing or changed upstream confirmation trace')
    return ref, path


def key(out, case, method, repeat=0, attempt=0):
    cell = cell_id(case)
    if not repeat:
        return out/'audit'/f'{cell}_{method}.json'
    return out/'timing'/f'{cell}_r{repeat}_a{attempt}_{method}.json'


def work(opts, out, source, manifest, identity, cases):
    i, method, repeat, attempt = opts.worker
    case = cases[int(i)]
    cell = cell_id(case)
    ref, _ = reference(source, case, manifest['references'][cell])
    bank_path = source/'banks'/f'{case["seed"]}.json'
    snapshot = out/'preparation'/f'{cell}.json'
    prep = sealed(snapshot)
    require(manifest['environment'] == environment() and prep['manifest'] == identity and
            sha(bank_path) == manifest['banks'][str(case['seed'])], 'Worker inputs changed')
    if int(repeat):
        audited = sealed(out/'audited.json')
        require(audited['manifest'] == identity, 'Timing requires a sealed audit')
    result = run(source, ref, config(opts.preset, case['seed']), snapshot, sealed(bank_path),
                 method, audit=not int(repeat))
    output = key(out, case, method, int(repeat), int(attempt))
    seal(output, dict(manifest=identity, case=case, method=method, repeat=int(repeat), attempt=int(attempt), **result))


def execute(opts, out, source):
    cases, blocks, references = upstream(source, opts.preset)
    marker = out/'manifest.json'
    if opts.worker:
        manifest = read(marker)
        require(manifest['source'] == str(source) and manifest['preset'] == opts.preset
                and manifest['upstream_complete'] == sha(source/'completed.json'), 'Reference manifest changed')
        work(opts, out, source, manifest, sha(marker), cases)
        return
    refs, banks = {}, {}
    for case in cases:
        cell = cell_id(case)
        ref, path = reference(source, case, references[cell])
        require(ref['cfg'] == dict(config(opts.preset, case['seed']), public_size=case['public_size']) and
                raw_sha(path.with_suffix('.npz')) == ref['payload_sha256'], f'Invalid trace payload for {cell}')
        refs[cell] = ref
        seed = str(case['seed'])
        if seed not in banks:
            bank_path = source/'banks'/f'{seed}.json'
            verify_bank(bank_path)
            banks[seed] = sha(bank_path)
    manifest = dict(preset=opts.preset, source=str(source), cases=cases, schedule=blocks, banks=banks,
                    upstream_complete=sha(source/'completed.json'),
                    references={cell: references[cell] for cell in refs}, environment=environment(),
                    dependencies=sources(), package={p.name: sha(p) for p in sorted(PACKAGE.glob('*.py'))},
                    config_source=sha(PACKAGE.parent/'confirmation/run.py'), design_sha=sha(PACKAGE/'README.md'),
                    savings_threshold=.03, min_wins=2, seeds_per_partition=2)
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires the same source, environment and code')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a fresh output directory')
        write(marker, manifest)
    identity = sha(marker)
    done = out/'completed.json'
    completion = sealed(done) if receipt(done).is_file() else None

    def invoke(case, method, repeat=0, attempt=0):
        print(f'{cell_id(case)} {method} ' + (f'timing r{repeat} attempt {attempt}' if repeat else 'audit'), flush=True)
        subprocess.run([sys.executable, '-B', '-m', 'snapshot_routing.full_training.run', '--preset', opts.preset,
                        '--source', str(source), '--output', str(out), '--worker', str(cases.index(case)),
                        method, str(repeat), str(attempt)], cwd=ROOT, check=True)

    def verified(case, method, repeat=0, attempt=0):
        path = key(out, case, method, repeat, attempt)
        r = sealed(path)
        cfg = refs[cell_id(case)]['cfg']
        require((r['manifest'], r['case'], r['method'], r['repeat'], r['attempt']) ==
                (identity, case, method, repeat, attempt) and len(r['observed']) == cfg['rounds'],
                f'Invalid worker result: {path}')
        if repeat:
            require(len(r['timing']) == cfg['rounds'] and not r['evaluations'] and r['comparisons'] == 0 and
                    r['setup_seconds'] > 0, f'Invalid timing record: {path}')
        else:
            require(r['comparisons'] == refs[cell_id(case)]['comparisons'] and
                    [e['round'] for e in r['evaluations']] == checkpoints(cfg), f'Incomplete audit: {path}')
        return r, path

    audit_runs, audit_hashes, preparations = {}, {}, {}
    for case in cases:
        cell = cell_id(case)
        prep_path = out/'preparation'/f'{cell}.json'
        if not receipt(prep_path).is_file():
            require(completion is None, 'Completed experiment lost preparation')
            prepare_snapshot(source, refs[cell], config(opts.preset, case['seed']), prep_path, identity)
        prep = sealed(prep_path)
        require(prep['manifest'] == identity and prep['model_sha'] == sha(prep_path.with_suffix('.pt')),
                'Preparation changed')
        preparations[cell] = prep
        for method in METHODS:
            if not receipt(key(out, case, method)).is_file():
                require(completion is None, 'Completed experiment lost an audit')
                invoke(case, method)
            record, path = verified(case, method)
            if cell in audit_runs:
                require(record['observed'] == audit_runs[cell]['observed'] and
                        record['evaluations'] == audit_runs[cell]['evaluations'],
                        f'Trajectory mismatch: {cell} {method}')
            else:
                audit_runs[cell] = record
            audit_hashes[path.relative_to(out).as_posix()] = sha(path)
        audit_hashes[prep_path.relative_to(out).as_posix()] = sha(prep_path)
    audited_path = out/'audited.json'
    audit_record = dict(manifest=identity, hashes=audit_hashes)
    if receipt(audited_path).is_file():
        require(sealed(audited_path) == audit_record, 'Audited evidence changed')
    else:
        require(completion is None, 'Completed experiment lost audit seal')
        seal(audited_path, audit_record)

    result, hashes = [], {}
    for block in blocks:
        case, repeat = block['case'], block['repeat']
        cell = cell_id(case)
        for attempt in (0, 1):
            block_path = out/'blocks'/f'{cell}_r{repeat}_a{attempt}.json'
            previous = sealed(block_path) if receipt(block_path).is_file() else None
            require(previous is not None or completion is None, 'Completed experiment lost a timing block')
            paths, group = {}, []
            for method in block['order']:
                if previous is None:
                    # Restart a partial block as a full matched set in its specified order.
                    invoke(case, method, repeat, attempt)
                record, path = verified(case, method, repeat, attempt)
                require(record['observed'] == audit_runs[cell]['observed'], f'Timed trajectory differs: {path}')
                paths[path.relative_to(out).as_posix()] = sha(path)
                group.append(record)
            block_record = dict(manifest=identity, block=block, attempt=attempt, runs=paths)
            if previous is None:
                seal(block_path, block_record)
            else:
                require(previous == block_record, f'Changed timing block: {block_path}')
            result.extend(group)
            hashes[block_path.relative_to(out).as_posix()] = sha(block_path)
            interrupted = any(r['suspend_seconds'] is not None and r['suspend_seconds'] >= 1. for r in group)
            if not interrupted:
                break
    final = dict(manifest=identity, audit=sha(audited_path), blocks=hashes)
    require(completion is None or completion == final, 'Completion evidence changed')
    report(out, result, preparations, list(audit_runs.values()), manifest)
    seal(done, final)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=4, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    default_source = ('snapshot_routing_confirmation_full' if opts.preset == 'full'
                      else 'snapshot_routing_confirmation_release_smoke')
    source = (opts.source or ROOT/'outputs'/default_source).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_training_{opts.preset}').resolve()
    require(not (out.is_relative_to(source) or source.is_relative_to(out)), 'Output overlaps source')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, source)


if __name__ == '__main__':
    main()
