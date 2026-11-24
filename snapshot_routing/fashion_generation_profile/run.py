"""Attribute Fashion-MNIST relation-generation time on the E55 workload."""

import argparse
from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import sleep
from unittest.mock import patch

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.noniid_clustering import data
from experiments.snapshot_certification_timing.design import (
    ROOT, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_certification_timing.worker import battery, suspend_clock
from ..fashion_confirmation import worker as fashion
from ..fashion_confirmation.design import cell_id, configuration, design
from ..paired_boundaries.run import check_or_seal
from ..report import eligible
from .phases import factory
from .report import report

MODULE = 'snapshot_routing.fashion_generation_profile.run'
METHODS = ('B', 'D')


def groups(cases, repeats):
    for repeat in range(1, repeats+1):
        for offset in range(len(cases)):
            i = (offset+repeat-1) % len(cases)
            yield cases[i], 'timing', repeat, METHODS if (i+repeat) % 2 else METHODS[::-1]
    for i, case in enumerate(cases):
        yield case, 'profile', 1, METHODS if i % 2 == 0 else METHODS[::-1]


def run_path(out, cell, stage, repeat, attempt, method):
    return out/'runs'/f'{cell}_{stage}_{repeat}_{attempt}_{method}.json'


def worker(opts, cfg, manifest, identity):
    cell, stage, repeat, attempt, method = opts.worker
    repeat, attempt = int(repeat), int(attempt)
    require(environment() == manifest['environment'] and opts.preset == manifest['preset'],
            'Worker environment differs from manifest')
    require(sources() == manifest['sources']
            and all(sha(ROOT/path) == checksum for path, checksum in manifest['code'].items()),
            'Experiment source changed after the manifest was written')
    require(cell in manifest['inputs'] and stage in ('audit', 'timing', 'profile') and method in METHODS,
            'Unknown worker case')
    cache = Path(manifest['inputs'][cell]['path'])
    require(sha(cache/'prepared.json') == manifest['inputs'][cell]['sha256'], 'Prepared manifest changed')
    rows = []
    observer = (patch.object(fashion, 'generator', factory(rows, len(cfg.dimensions)))
                if stage == 'profile' else nullcontext())
    with observer:
        result = fashion.run(cache, cfg, method, audit=stage == 'audit')
    seal(run_path(opts.output, cell, stage, repeat, attempt, method),
         dict(identity=identity, cell=cell, stage=stage, repeat=repeat, attempt=attempt,
              method=method, profile_rows=rows, **result))


def validate(record, audit, cfg):
    for field in ('initial', 'observed', 'traffic'):
        require(record[field] == audit[field],
                f'{record["cell"]} {record["method"]}: {field} differs from full B audit')
    rounds = list(range(1, cfg.rounds+1))
    require([r['round'] for r in record['timing']] == rounds, 'Incomplete timing trace')
    rows = record['profile_rows']
    if record['stage'] == 'profile':
        clients = range(len(cfg.dimensions))
        require([(r['round'], r['client'], r['width']) for r in rows] ==
                [(rnd, c, cfg.dimensions[c]) for rnd in rounds for c in clients], 'Incomplete phase trace')
        require([sum(r['forward_endpoints'] for r in rows if r['client'] == c) for c in clients]
                == record['client_endpoints'], 'Phase and full-run endpoint counts differ')
    else:
        require(not rows, 'Primary timing includes profiling')


def publish_cache(staged, destination):
    for attempt in range(5):
        try:
            staged.rename(destination)
            return
        except PermissionError as error:
            # Windows file scanners can temporarily hold files just written by preparation.
            if getattr(error, 'winerror', None) not in (5, 32) or attempt == 4 or destination.exists():
                raise
            sleep(0.2 * (attempt+1))


def inputs_for(opts, cfg, cases, existing):
    out = opts.output
    if opts.cache_dir is None:
        data.ensure_data(opts.data_dir)
    inputs = {}
    for case in cases:
        cell = cell_id(case)
        root = opts.cache_dir or out/'cache'
        cache = root/cell
        if not cache.is_dir():
            require(existing is None and opts.cache_dir is None, f'Missing prepared cache: {cache}')
            root.mkdir(parents=True, exist_ok=True)
            print(f'Preparing {cell}', flush=True)
            with TemporaryDirectory(dir=root) as tmp:
                staged = data.prepare(Path(tmp), opts.data_dir, cfg, case['seed'], case['partition'])
                publish_cache(staged, cache)
        data.verify(cache, cfg, case['seed'], case['partition'])
        inputs[cell] = dict(path=str(cache), sha256=sha(cache/'prepared.json'))
    return inputs


def execute(opts):
    out = opts.output
    cfg = configuration(opts.preset)
    cfg.validate()
    marker = out/'manifest.json'
    if opts.worker:
        worker(opts, cfg, read(marker), sha(marker))
        return
    require(opts.preset == 'smoke' or (battery() is True and suspend_clock() is not None),
            'Full timing requires observable AC power and suspend time. Use smoke to validate the workflow.')
    existing = read(marker) if marker.is_file() else None
    require(opts.resume if existing else not out.exists() or not any(out.iterdir()) or (
        opts.resume and opts.cache_dir is None and {p.name for p in out.iterdir()} == {'cache'}),
            'Use an empty output directory or --resume with the original inputs')
    cases, _ = design(opts.preset)
    repeats = 4 if opts.preset == 'full' else 1
    inputs = inputs_for(opts, cfg, cases, existing)
    package = Path(__file__).resolve().parent
    dependencies = [*package.glob('*.py'), package/'README.md',
                    *sorted((package.parent/'fashion_confirmation').glob('*.py')),
                    package.parent/'report.py', package.parent/'paired_boundaries/run.py']
    manifest = dict(preset=opts.preset, cases=cases, repeats=repeats, config=cfg.json(), inputs=inputs,
                    environment=environment(), sources=sources(),
                    code={p.relative_to(ROOT).as_posix(): sha(p) for p in dependencies})
    if existing is None:
        write(marker, manifest)
    else:
        require(manifest == existing, 'Resume requires identical prepared data, environment and code')
    identity = sha(marker)

    def launch(cell, stage, repeat, attempt, method):
        print(f'{cell} {stage} block={repeat} attempt={attempt} {method}', flush=True)
        subprocess.run([sys.executable, '-B', '-m', MODULE, '--preset', opts.preset,
                        '--output', str(out), '--worker', cell, stage, str(repeat), str(attempt), method],
                       cwd=ROOT, check=True)

    def load(cell, stage, repeat, attempt, method):
        path = run_path(out, cell, stage, repeat, attempt, method)
        record = sealed(path)
        require((record['identity'], record['cell'], record['stage'], record['repeat'],
                 record['attempt'], record['method']) == (identity, cell, stage, repeat, attempt, method),
                f'Unexpected run identity: {path}')
        return record

    audits, hashes = {}, {}
    for case in cases:
        cell = cell_id(case)
        path = run_path(out, cell, 'audit', 0, 0, 'B')
        if not receipt(path).is_file():
            launch(cell, 'audit', 0, 0, 'B')
        audit = load(cell, 'audit', 0, 0, 'B')
        require(len(audit['observed']) == cfg.rounds and
                audit['comparisons'] == cfg.rounds*(cfg.samples//2)*len(cfg.dimensions), 'Incomplete B audit')
        audits[cell] = audit
        hashes[path.relative_to(out).as_posix()] = sha(path)

    blocks = []
    for case, stage, repeat, order in groups(cases, repeats):
        cell = cell_id(case)
        for attempt in range(2):
            block_path = out/'blocks'/f'{cell}_{stage}_{repeat}_{attempt}.json'
            if not receipt(block_path).is_file():
                # Keep both runs adjacent, including when resuming a partial block.
                for method in order:
                    launch(cell, stage, repeat, attempt, method)
            pair = {method: load(cell, stage, repeat, attempt, method) for method in order}
            for run in pair.values():
                validate(run, audits[cell], cfg)
            clean = eligible(pair, opts.preset)
            record = dict(cell=cell, stage=stage, repeat=repeat, attempt=attempt, order=list(order), eligible=clean,
                          hashes={method: sha(run_path(out, cell, stage, repeat, attempt, method)) for method in order})
            check_or_seal(block_path, record, None)
            hashes[block_path.relative_to(out).as_posix()] = sha(block_path)
            blocks.append((record, pair))
            if clean:
                break

    report_files, complete = report(out, manifest, blocks)
    check_or_seal(out/'completed.json',
                  dict(manifest=identity, records=hashes, reports=report_files, eligible_complete=complete), None)
    print(f'Report: {out/"report.md"}', flush=True)
    require(complete, 'One or more cells lack eligible pairs. See the report and use a new output for a retest.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--data-dir', type=Path, default=ROOT/'experiments/real_iid/data')
    parser.add_argument('--cache-dir', type=Path, help='E55 cache root (contains one directory per seed/partition)')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=5, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    opts.output = (opts.output or ROOT/'outputs'/f'fashion_generation_profile_{opts.preset}').resolve()
    opts.data_dir = opts.data_dir.resolve()
    if opts.cache_dir is not None:
        opts.cache_dir = opts.cache_dir.resolve()
    for source in (p for p in (opts.data_dir, opts.cache_dir) if p is not None):
        require(not (source.is_relative_to(opts.output) or opts.output.is_relative_to(source)),
                f'Output overlaps input: {source}')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts)


if __name__ == '__main__':
    main()
