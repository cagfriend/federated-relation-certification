"""Screen a D row-collection change, then confirm it on held-out E55 workloads."""

import argparse
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (
    ROOT, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_certification_timing.worker import battery, suspend_clock
from ..fashion_confirmation import worker as fashion
from ..fashion_confirmation.design import PARTITIONS, SEEDS, cell_id, configuration
from ..fashion_generation_profile.run import inputs_for
from ..paired_boundaries.run import check_or_seal
from ..report import eligible
from .gather import BASE, Collector, generator_factory
from .report import confirmation_report, screening_report
from .screening import ORDERS, screen, select

PACKAGE = Path(__file__).resolve().parent
MODULE = 'snapshot_routing.fashion_gather_optimization.run'
HELD_OUT = (3111, 3112, 3113)
AUDIT_FIELDS = ('initial', 'observed', 'traffic')


def cases_for(seeds, partitions, preset):
    return [dict(seed=seed, partition=part) for seed in (seeds if preset == 'full' else seeds[:1])
            for part in partitions]


def blocks_for(cases, preset):
    for repeat, order in enumerate(ORDERS if preset == 'full' else ORDERS[:1], 1):
        for offset in range(len(cases)):
            i = (offset+repeat-1) % len(cases)
            rotated = ORDERS[(ORDERS.index(order)+i) % len(ORDERS)]
            names = dict(zip(ORDERS[0], ('B', BASE, 'optimized'), strict=True))
            yield cell_id(cases[i]), repeat, tuple(names[m] for m in rotated)


def run_worker(opts, stage, cell, role, method, repeat, attempt, cfg):
    root = opts.output/stage
    manifest = read(root/'manifest.json')
    cache = manifest['inputs'][cell]
    require(manifest['environment'] == environment()
            and manifest['preset'] == opts.preset
            and manifest['sources'] == sources()
            and all(sha(ROOT/path) == digest for path, digest in manifest['code'].items())
            and sha(Path(cache['path'])/'prepared.json') == cache['sha256'],
            'Worker input, sources or environment changed')
    identity = sha(root/'manifest.json')
    path = Path(cache['path'])
    if stage == 'screening':
        result = screen(path, cfg, opts.preset)
    else:
        chosen = manifest['candidate'] if method == 'optimized' else method
        collector = Collector(chosen if chosen != 'B' else BASE, cfg.samples, cfg.dimensions)
        observed_cache, refreshed = [], []

        def request(rnd, client, features, ids, weights, bias):
            refreshed.append(dict(round=rnd, client=client, ids=fashion.digest(ids), count=len(ids)))

        observe = role == 'audit' and method != 'B'
        if observe or method == 'optimized':
            factory = generator_factory(chosen, collector, on_refresh=request if observe else None,
                                        cache_rows=observed_cache if observe else None)
            with patch.object(fashion, 'generator', factory):
                result = fashion.run(path, cfg, BASE, audit=role == 'audit')
        else:
            result = fashion.run(path, cfg, method, audit=role == 'audit')
        result.update(scratch_bytes=collector.nbytes, cache_trace=observed_cache, refresh_trace=refreshed)
    seal(run_path(root, cell, role, method, repeat, attempt),
         dict(identity=identity, cell=cell, role=role, method=method, repeat=repeat, attempt=attempt, **result))


def run_path(root, cell, role, method, repeat, attempt):
    return root/'runs'/f'{cell}_{role}_{repeat}_{attempt}_{method}.json'


def manifest_for(opts, stage, cases, cfg, code, *, cache_dir=None, **extra):
    root = opts.output/stage
    path = root/'manifest.json'
    inputs = inputs_for(SimpleNamespace(output=root, cache_dir=cache_dir, data_dir=opts.data_dir),
                        cfg, cases, read(path) if path.is_file() else None)
    value = dict(preset=opts.preset, cases=cases, config=cfg.json(), inputs=inputs,
                 environment=environment(), sources=sources(), code=code, **extra)
    check_or_seal(path, value, None)
    return value, sha(path)


def check_audits(audits, cfg, cell):
    b, old, new = (audits[method] for method in ('B', BASE, 'optimized'))
    expected = cfg.rounds * (cfg.samples//2) * len(cfg.dimensions)
    clients = range(len(cfg.dimensions))
    for run in (b, old, new):
        require(run['comparisons'] == expected and len(run['observed']) == cfg.rounds
                and all(run[key] == b[key] for key in (*AUDIT_FIELDS, 'evaluations')),
                f'{cell}: incomplete audit or differing student trajectory')
    for key, start in [('cache_trace', 1), ('refresh_trace', 2)]:
        require(old[key] == new[key] and [(row['round'], row['client']) for row in old[key]] ==
                [(rnd, c) for rnd in range(start, cfg.rounds+1) for c in clients],
                f'{cell}: old D and optimized D disagree on refresh or cache state')
    require(old['client_endpoints'] == new['client_endpoints'], f'{cell}: changed refresh work')


def execute(opts):
    cfg = configuration(opts.preset)
    cfg.validate()
    if opts.worker:
        stage, cell, role, method, repeat, attempt = opts.worker
        run_worker(opts, stage, cell, role, method, int(repeat), int(attempt), cfg)
        return
    require(opts.preset == 'smoke' or (battery() is True and suspend_clock() is not None),
            'Full timing requires observable AC power and suspend time')
    out = opts.output
    require(opts.resume or not out.exists() or not any(out.iterdir()), 'Use a new output or add --resume')
    shared = ('fashion_confirmation/design.py', 'fashion_confirmation/worker.py',
              'fashion_generation_profile/run.py', 'fashion_generation_profile/phases.py',
              'fashion_confirmation/report.py', 'report.py', 'paired_boundaries/run.py')
    dependencies = [*PACKAGE.glob('*.py'), PACKAGE/'README.md', *(PACKAGE.parent/p for p in shared)]
    code = {p.relative_to(ROOT).as_posix(): sha(p) for p in dependencies}

    def launch(stage, cell, role, method, repeat=0, attempt=0):
        print(f'{stage} {cell} {role} {method} block={repeat} attempt={attempt}', flush=True)
        subprocess.run([sys.executable, '-B', '-m', MODULE, '--preset', opts.preset, '--output', str(out),
                        '--worker', stage, cell, role, method, str(repeat), str(attempt)], cwd=ROOT, check=True)

    def load(root, identity, cell, role, method, repeat=0, attempt=0):
        path = run_path(root, cell, role, method, repeat, attempt)
        run = sealed(path)
        require((run['identity'], run['cell'], run['role'], run['method'], run['repeat'], run['attempt'])
                == (identity, cell, role, method, repeat, attempt), f'Unexpected run identity: {path}')
        return run, sha(path)

    dev = cases_for(SEEDS, ('dirichlet_0.1',), opts.preset)
    root = out/'screening'
    _, identity = manifest_for(opts, 'screening', dev, cfg, code, cache_dir=opts.development_cache)
    screened, hashes = {}, {}
    for case in dev:
        cell = cell_id(case)
        if not receipt(run_path(root, cell, 'replay', BASE, 0, 0)).is_file():
            launch('screening', cell, 'replay', BASE)
        screened[cell], hashes[cell] = load(root, identity, cell, 'replay', BASE)
    status, candidate, rows = select(screened, opts.preset)
    selection = root/'selection.json'
    reports = screening_report(root, screened, rows, status, candidate)
    check_or_seal(selection, dict(manifest=identity, status=status, candidate=candidate,
                                  runs=hashes, reports=reports), None)
    print(f'Screening: {status}. Report: {root/"report.md"}', flush=True)
    if candidate is None:
        check_or_seal(out/'completed.json', dict(screening=sha(selection), status=status), None)
        require(status != 'screen_incomplete', 'Screening has incomplete timing blocks. Use a new output for a retest.')
        return

    held_out = cases_for(HELD_OUT, PARTITIONS, opts.preset)
    root = out/'confirmation'
    manifest, identity = manifest_for(opts, 'confirmation', held_out, cfg, code,
                                      candidate=candidate, screening=sha(selection))
    audits, hashes = {}, {}
    for case in held_out:
        cell = cell_id(case)
        for method in ('B', BASE, 'optimized'):
            if not receipt(run_path(root, cell, 'audit', method, 0, 0)).is_file():
                launch('confirmation', cell, 'audit', method)
            audits[cell, method], hashes[f'{cell}_{method}'] = load(root, identity, cell, 'audit', method)
        check_audits({m: audits[cell, m] for m in ('B', BASE, 'optimized')}, cfg, cell)

    timing = []
    for cell, repeat, order in blocks_for(held_out, opts.preset):
        for attempt in range(2):
            path = root/'blocks'/f'{cell}_{repeat}_{attempt}.json'
            if not receipt(path).is_file():
                for method in order:
                    launch('confirmation', cell, 'timing', method, repeat, attempt)
            runs, run_hashes = {}, {}
            for method in order:
                run, digest = load(root, identity, cell, 'timing', method, repeat, attempt)
                audit = audits[cell, method]
                require(all(run[k] == audit[k] for k in (*AUDIT_FIELDS, 'client_endpoints', 'scratch_bytes')),
                        f'{cell} {method}: timed path differs from its audit')
                require(not run['cache_trace'] and not run['refresh_trace'] and not run['comparisons']
                        and not run['evaluations']
                        and [row['round'] for row in run['timing']] == list(range(1, cfg.rounds+1)),
                        f'{cell} {method}: invalid timing window')
                runs[method], run_hashes[method] = run, digest
            clean = eligible(runs, opts.preset)
            block = dict(cell=cell, repeat=repeat, attempt=attempt, order=list(order), eligible=clean)
            check_or_seal(path, dict(manifest=identity, hashes=run_hashes, **block), None)
            hashes[path.relative_to(root).as_posix()] = sha(path)
            timing.append((block, runs))
            if clean:
                break
    reports, verdict = confirmation_report(root, manifest, timing)
    check_or_seal(out/'completed.json', dict(screening=sha(selection), confirmation=identity,
                                            status=verdict, records=hashes, reports=reports), None)
    print(f'Confirmation: {verdict}. Report: {root/"report.md"}', flush=True)
    require(verdict != 'confirmation_incomplete', 'Confirmation has incomplete blocks. Use a new output for a retest.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'experiments/real_iid/data')
    parser.add_argument('--development-cache', type=Path, help='Prepared cache root from the matching E55 workload')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=6, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    opts.output = (opts.output or ROOT/'outputs'/f'fashion_gather_optimization_{opts.preset}').resolve()
    opts.data_dir = opts.data_dir.resolve()
    if opts.development_cache is None and not opts.worker:
        default = ROOT/'outputs'/f'fashion_generation_profile_{opts.preset}'/'cache'
        if default.is_dir():
            opts.development_cache = default
    if opts.development_cache is not None:
        opts.development_cache = opts.development_cache.resolve()
    for source in (opts.data_dir, opts.development_cache):
        if source is not None:
            require(not (opts.output.is_relative_to(source) or source.is_relative_to(opts.output)),
                    f'Output overlaps input: {source}')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts)


if __name__ == '__main__':
    main()
