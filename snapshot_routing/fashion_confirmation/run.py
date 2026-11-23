"""Confirm current D against full B and same-bound E on real Fashion-MNIST."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.noniid_clustering import data
from experiments.snapshot_certification_timing.design import (
    ROOT, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from ..paired_boundaries.run import check_or_seal
from .design import GUARD, HEAD_THRESHOLD, METHODS, PUBLIC_STEPS, PUBLIC_WEIGHTS, cell_id, configuration, design
from .report import report
from .worker import run

PACKAGE = Path(__file__).resolve().parent
MODULE = 'snapshot_routing.fashion_confirmation.run'


def path_for(out, case, method, repeat=0, attempt=0):
    cell = cell_id(case)
    if repeat:
        return out/'timing'/f'{cell}_r{repeat}_a{attempt}_{method}.json'
    return out/'audit'/f'{cell}_{method}.json'


def worker(opts, out, manifest, identity):
    index, method, repeat, attempt = opts.worker
    case = manifest['cases'][int(index)]
    cfg = configuration(opts.preset)
    repeat, attempt = int(repeat), int(attempt)
    require(manifest['preset'] == opts.preset and manifest['data_dir'] == str(opts.data_dir)
            and environment() == manifest['environment'], 'Worker context differs from the run manifest')
    cache = out/'cache'/cell_id(case)
    if method == 'prepare':
        cache.parent.mkdir(exist_ok=True)
        with TemporaryDirectory(dir=cache.parent) as tmp:
            prepared = data.prepare(Path(tmp), opts.data_dir, cfg, case['seed'], case['partition'])
            prepared.rename(cache)
        return
    require(method in METHODS, 'Unknown method')
    common = sealed(out/'prepared.json')
    require(common['manifest'] == identity and common['hashes'][cell_id(case)] == sha(cache/'prepared.json'),
            'Prepared inputs changed')
    if repeat:
        require(sealed(out/'audited.json')['manifest'] == identity, 'Timing requires passed audit')
    result = run(cache, cfg, method, audit=not repeat)
    seal(path_for(out, case, method, repeat, attempt),
         dict(manifest=identity, case=case, repeat=repeat, attempt=attempt, method=method, **result))


def read_run(out, cfg, identity, case, method, repeat=0, attempt=0):
    path = path_for(out, case, method, repeat, attempt)
    result = sealed(path)
    require((result['manifest'], result['case'], result['method'], result['repeat'], result['attempt']) ==
            (identity, case, method, repeat, attempt) and len(result['observed']) == cfg.rounds and
            len(result['client_endpoints']) == len(cfg.dimensions), f'Invalid run: {path}')
    if repeat:
        require([row['round'] for row in result['timing']] == list(range(1, cfg.rounds+1)) and
                not result['comparisons'] and not result['evaluations'], f'Incomplete timing: {path}')
    else:
        require(result['comparisons'] == cfg.rounds*(cfg.samples//2)*len(cfg.dimensions) and
                [row['round'] for row in result['evaluations']] ==
                [0, *(i for i in range(1, cfg.rounds+1) if i % cfg.eval_every == 0 or i == cfg.rounds)],
                f'Incomplete audit: {path}')
    return path, result


def compare(expected, actual, path):
    fields = ('initial', 'traffic', 'observed', 'client_endpoints')
    require(all(actual[key] == expected[key] for key in fields), f'Timed path differs from its audit: {path}')


def execute(opts, out):
    marker = out/'manifest.json'
    if opts.worker:
        worker(opts, out, read(marker), sha(marker))
        return
    cfg = configuration(opts.preset)
    cfg.validate()
    cases, blocks = design(opts.preset)
    data.ensure_data(opts.data_dir, download=False)
    local_code = [PACKAGE/'README.md', *sorted(PACKAGE.glob('*.py')), PACKAGE.parent/'report.py',
                  PACKAGE.parent/'paired_boundaries/run.py']
    manifest = dict(preset=opts.preset, cases=cases, blocks=blocks, config=cfg.json(), data_dir=str(opts.data_dir),
                    raw_files={name: sha(opts.data_dir/name) for name in data.FILES},
                    public_steps=PUBLIC_STEPS, public_weights=list(PUBLIC_WEIGHTS), guard=GUARD,
                    threshold_pct=HEAD_THRESHOLD, minimum_wins=2,
                    environment=environment(), dependencies=sources(),
                    code={path.relative_to(ROOT).as_posix(): sha(path) for path in local_code})
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical inputs and sources')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a new output directory')
        write(marker, manifest)
    identity = sha(marker)
    finished = out/'completed.json'
    completed = sealed(finished) if receipt(finished).is_file() else None

    def launch(case, method, repeat=0, attempt=0):
        print(f'{cell_id(case)} {method} block={repeat} attempt={attempt}', flush=True)
        subprocess.run([sys.executable, '-B', '-m', MODULE, '--preset', opts.preset, '--output', str(out),
                        '--data-dir', str(opts.data_dir), '--worker', str(cases.index(case)),
                        method, str(repeat), str(attempt)], cwd=ROOT, check=True)

    caches, partitions = {}, {}
    for case in cases:
        cell = cell_id(case)
        cache = out/'cache'/cell
        if not cache.is_dir():
            require(completed is None, 'Completed experiment lost a feature cache')
            launch(case, 'prepare')
        data.verify(cache, cfg, case['seed'], case['partition'])
        caches[cell] = sha(cache/'prepared.json')
        partitions[cell] = read(cache/'partition.json')['diagnostics']
    prepared = out/'prepared.json'
    check_or_seal(prepared, dict(manifest=identity, hashes=caches, partitions=partitions), completed)
    audits, hashes, public_ids = {}, {}, {}
    for case in cases:
        cell = cell_id(case)
        for method in METHODS:
            if not receipt(path_for(out, case, method)).is_file():
                require(completed is None, 'Completed experiment lost an audit')
                launch(case, method)
            path, record = read_run(out, cfg, identity, case, method)
            audits[cell, method] = record
            b = audits[cell, 'B']
            require(all(record[key] == b[key] for key in ('initial', 'observed', 'evaluations', 'traffic')),
                    f'{cell} {method}: outcomes differ from full B')
            signature = (b['initial']['graph'], b['initial']['public_ids'])
            require(public_ids.setdefault(case['seed'], signature) == signature, 'Public inputs differ across partitions')
            hashes[path.relative_to(out).as_posix()] = sha(path)
    audited = out/'audited.json'
    check_or_seal(audited, dict(manifest=identity, prepared=sha(prepared), hashes=hashes), completed)

    results, hashes = [], {}
    for block in blocks:
        case, repeat = block['case'], block['repeat']
        cell = cell_id(case)
        for attempt in (0, 1):
            path = out/'blocks'/f'{cell}_r{repeat}_a{attempt}.json'
            exists = receipt(path).is_file()
            require(exists or completed is None, 'Completed experiment lost a timing block')
            runs, timing_hashes = {}, {}
            for method in block['order']:
                if not exists:
                    launch(case, method, repeat, attempt)
                saved, result = read_run(out, cfg, identity, case, method, repeat, attempt)
                compare(audits[cell, method], result, saved)
                timing_hashes[method] = sha(saved)
                runs[method] = {key: value for key, value in result.items() if key != 'observed'}
            check_or_seal(path, dict(manifest=identity, block=block, attempt=attempt, runs=timing_hashes), completed)
            hashes[path.relative_to(out).as_posix()] = sha(path)
            results.append((block, attempt, runs))
            if opts.preset == 'smoke' or not any((row['suspend_seconds'] or 0.) >= 1. for row in runs.values()):
                break
    reports = report(out, manifest, results, audits)
    check_or_seal(finished, dict(manifest=identity, audit=sha(audited), blocks=hashes, reports=reports), completed)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preset', choices=('full', 'smoke'), default='full')
    p.add_argument('--data-dir', type=Path, default=ROOT/'experiments/real_iid/data')
    p.add_argument('--output', type=Path)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--worker', nargs=4, help=argparse.SUPPRESS)
    opts = p.parse_args()
    opts.data_dir = opts.data_dir.resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_fashion_confirmation_{opts.preset}').resolve()
    require(not (out.is_relative_to(opts.data_dir) or opts.data_dir.is_relative_to(out)), 'Output overlaps input data')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out)


if __name__ == '__main__':
    main()
