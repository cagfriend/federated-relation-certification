"""Compare B, same-bound E, default D and Demand on paired STL-10 training."""

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
from experiments.snapshot_graph_scaling.design import cell_id, context_id
from experiments.snapshot_graph_scaling.inputs import raw_sha, verify_bank
from ..confirmation.capture import capture_seed
from ..confirmation.run import DATA_FILES, config, trace_record
from ..full_training.worker import prepare_snapshot
from ..on_demand.run import path_for
from ..on_demand.worker import student_trace
from .design import METHODS, schedule
from .report import report
from .worker import run

PACKAGE = Path(__file__).resolve().parent
MODULE = 'snapshot_routing.paired_boundaries.run'
SHARED = ('confirmation/capture.py', 'confirmation/run.py', 'full_training/worker.py', 'on_demand/engine.py',
          'on_demand/worker.py', 'on_demand/protocol.py', 'on_demand/run.py', 'on_demand/report.py', 'report.py')


def source_for(out, confirmation, case, manifest):
    return out/'fresh' if case in manifest['fresh'] else confirmation


def reference(out, confirmation, case, manifest, identity):
    source = source_for(out, confirmation, case, manifest)
    anchor = identity if source == out/'fresh' else manifest['historical_manifest']
    payload, ref = trace_record(source, case, anchor, manifest['protocol'])
    if source != out/'fresh':
        require(sha(payload.with_suffix('.json')) == manifest['historical_traces'][cell_id(case)],
                'Historical trace changed')
    return source, payload, ref


def worker(opts, out, confirmation, manifest, identity):
    protocol = manifest['protocol']
    require(manifest['preset'] == opts.preset and manifest['confirmation'] == str(confirmation)
            and manifest['environment'] == environment(), 'Worker context differs from manifest')
    if opts.capture is not None:
        fresh = out/'fresh'
        fresh.mkdir(exist_ok=True)
        cases = [c for c in manifest['fresh'] if c['seed'] == opts.capture]
        require(cases, 'Unknown fresh seed')
        pending = {cell_id(c) for c in cases if not receipt(fresh/'traces'/f'{cell_id(c)}.json').is_file()}
        capture_seed(fresh, config(protocol, opts.capture), cases, opts.data_dir,
                     manifest['raw_data'], identity, pending)
        return

    index, method, repeat, attempt = opts.worker
    case = manifest['cases'][int(index)]
    repeat, attempt = int(repeat), int(attempt)
    require(method in METHODS, 'Unknown timing path')
    source, payload, ref = reference(out, confirmation, case, manifest, identity)
    prep = out/'preparation'/f'{context_id(case)}.json'
    require(sealed(prep)['manifest'] == identity and ref['status'] == 'captured', 'Invalid selection input')
    common = sealed(out/'inputs.json')
    bank = source/'banks'/f"{case['seed']}.json"
    cell = cell_id(case)
    require(common['manifest'] == identity and sha(bank) == common['banks'][cell]
            and sha(payload.with_suffix('.json')) == common['traces'][cell], 'Worker inputs changed')
    if repeat:
        require(sealed(out/'audited.json')['manifest'] == identity, 'Timing requires completed audit')
    baseline = sealed(path_for(out, case, 'B')) if method == 'Demand' else None
    require(baseline is None or baseline['manifest'] == identity, 'Invalid B audit')
    result = run(source, ref, config(protocol, case['seed']), prep, sealed(bank), method, baseline, audit=not repeat)
    seal(path_for(out, case, method, repeat, attempt),
         dict(manifest=identity, case=case, method=method, repeat=repeat, attempt=attempt, **result))


def read_run(out, case, cfg, identity, method, repeat=0, attempt=0):
    path = path_for(out, case, method, repeat, attempt)
    run = sealed(path)
    require((run['manifest'], run['case'], run['method'], run['repeat'], run['attempt']) ==
            (identity, case, method, repeat, attempt) and len(run['observed']) == cfg['rounds'],
            f'Invalid record: {path}')
    if repeat:
        require(run['comparisons'] == 0 and run['setup_seconds'] > 0 and
                [r['round'] for r in run['timing']] == list(range(1, cfg['rounds']+1)),
                f'Incomplete timing: {path}')
    else:
        edges = sum(row['edges'] for row in run['scope']) if method == 'Demand' else cfg['rounds'] * (case['public_size']//2)
        require(run['comparisons'] == edges * len(cfg['widths']) and
                [r['round'] for r in run['evaluations']] == checkpoints(cfg), f'Incomplete audit: {path}')
    return path, run


def check_or_seal(path, value, completed):
    if receipt(path).is_file():
        require(sealed(path) == value, f'Record changed: {path}')
    else:
        require(completed is None, f'Completed run lost {path}')
        seal(path, value)


def execute(opts, out, confirmation):
    marker = out/'manifest.json'
    if opts.worker or opts.capture is not None:
        worker(opts, out, confirmation, read(marker), sha(marker))
        return
    cases, fresh, blocks = schedule(opts.preset)
    protocol = 'full' if opts.preset == 'full' else 'smoke'
    historical, historical_manifest = {}, None
    if len(cases) > len(fresh):
        path = confirmation/'manifest.json'
        historical_manifest = sha(path)
        prior = sealed(confirmation/'completed.json')
        require(prior['manifest'] == historical_manifest and read(path)['preset'] == protocol,
                'Need a completed E42 source with the matching protocol')
        historical = {cell_id(case): prior['traces'][cell_id(case)] for case in cases if case not in fresh}
    raw = {}
    if protocol == 'full':
        print('Checking STL-10 input hashes', flush=True)
        for name in DATA_FILES:
            raw[name] = raw_sha(opts.data_dir/name)
        require(raw == read(confirmation/'manifest.json')['raw_data'], 'STL-10 files differ from E42')
    manifest = dict(preset=opts.preset, protocol=protocol, cases=cases, fresh=fresh, blocks=blocks,
                    historical_manifest=historical_manifest, historical_traces=historical,
                    confirmation=str(confirmation), raw_data=raw, data_dir=str(opts.data_dir),
                    environment=environment(), dependencies=sources(), threshold_pct=3., minimum_wins=3,
                    code={path.relative_to(PACKAGE.parent).as_posix(): sha(path) for path in
                          [*sorted(PACKAGE.glob('*.py')), PACKAGE/'README.md', *(PACKAGE.parent/p for p in SHARED)]})
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical inputs and sources')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a new output directory')
        write(marker, manifest)
    identity = sha(marker)
    done_path = out/'completed.json'
    completed = sealed(done_path) if receipt(done_path).is_file() else None

    def launch(*argv):
        subprocess.run([sys.executable, '-B', '-m', MODULE, '--preset', opts.preset, '--output', str(out),
                        '--confirmation', str(confirmation), '--data-dir', str(opts.data_dir), *argv],
                       cwd=ROOT, check=True)

    for seed in sorted({c['seed'] for c in fresh}):
        if any(not receipt(out/'fresh'/'traces'/f'{cell_id(c)}.json').is_file() for c in fresh if c['seed'] == seed):
            require(completed is None, 'Completed run lost a fresh reference')
            launch('--capture', str(seed))

    blocked, refs, traces, banks = {}, {}, {}, {}
    for case in cases:
        cell = cell_id(case)
        source, payload, ref = reference(out, confirmation, case, manifest, identity)
        traces[cell] = sha(payload.with_suffix('.json'))
        if ref['status'] == 'initialization_blocked':
            blocked[cell] = ref['blocked_clients']
            continue
        require(raw_sha(payload) == ref['payload_sha256'], f'Invalid teacher trace: {cell}')
        bank = source/'banks'/f"{case['seed']}.json"
        bank_sha = sha(bank)
        if bank_sha not in banks.values():
            verify_bank(bank)
        banks[cell] = bank_sha
        refs[cell] = ref
    inputs_path = out/'inputs.json'
    check_or_seal(inputs_path, dict(manifest=identity, traces=traces, banks=banks, blocked=blocked), completed)

    audits, hashes = {}, {}
    for index, case in enumerate(cases):
        cell = cell_id(case)
        if cell in blocked:
            continue
        cfg = refs[cell]['cfg']
        prep = out/'preparation'/f'{context_id(case)}.json'
        if not receipt(prep).is_file():
            require(completed is None, 'Completed run lost a model snapshot')
            source = source_for(out, confirmation, case, manifest)
            prepare_snapshot(source, refs[cell], config(protocol, case['seed']), prep, identity)
        prepared = sealed(prep)
        require(prepared['manifest'] == identity and sha(prep.with_suffix('.pt')) == prepared['model_sha'],
                'Prepared encoder changed')
        hashes[prep.relative_to(out).as_posix()] = sha(prep)
        for method in METHODS:
            if not receipt(path_for(out, case, method)).is_file():
                require(completed is None, 'Completed run lost an audit')
                print(f'Audit {cell} {method}', flush=True)
                launch('--worker', str(index), method, '0', '0')
            path, audit = read_run(out, case, cfg, identity, method)
            audits[cell, method] = audit
            b = audits[cell, 'B']
            require(audit['evaluations'] == b['evaluations'], f'Audit quality changed: {cell} {method}')
            if method == 'Demand':
                require([student_trace(x) for x in audit['observed']] == [student_trace(x) for x in b['observed']],
                        f'Demand changed the student trajectory: {cell}')
            else:
                require(audit['observed'] == b['observed'] and audit['traffic'] == b['traffic'],
                        f'Full-graph trajectory or bytes differ: {cell} {method}')
            hashes[path.relative_to(out).as_posix()] = sha(path)
    audited = out/'audited.json'
    check_or_seal(audited, dict(manifest=identity, inputs=sha(inputs_path), hashes=hashes), completed)

    groups, hashes = [], {}
    for number, block in enumerate(blocks, 1):
        case, repeat = block['case'], block['repeat']
        cell = cell_id(case)
        if cell in blocked:
            continue
        cfg = refs[cell]['cfg']
        for attempt in (0, 1):
            path = out/'blocks'/f'{cell}_r{repeat}_a{attempt}.json'
            exists = receipt(path).is_file()
            require(exists or completed is None, 'Completed run lost a timing block')
            runs, run_hashes = {}, {}
            for method in block['order']:
                if not exists:
                    print(f'{number}/{len(blocks)} {cell} repeat={repeat} {method} attempt={attempt}', flush=True)
                    launch('--worker', str(cases.index(case)), method, str(repeat), str(attempt))
                run_path, run = read_run(out, case, cfg, identity, method, repeat, attempt)
                audit = audits[cell, method]
                fields = ('observed', 'traffic', 'scope', 'traffic_breakdown') if method == 'Demand' else ('observed', 'traffic')
                require(all(run[field] == audit[field] for field in fields) and
                        sum(row['endpoints'] for row in run['timing']) == sum(audit['client_endpoints']),
                        f'Timed trajectory or endpoints differ from audit: {run_path}')
                run_hashes[method] = sha(run_path)
                runs[method] = {k: v for k, v in run.items() if k != 'observed'}
            check_or_seal(path, dict(manifest=identity, block=block, attempt=attempt, runs=run_hashes), completed)
            hashes[path.relative_to(out).as_posix()] = sha(path)
            groups.append((block, attempt, runs))
            if protocol != 'full' or not any((r['suspend_seconds'] or 0.) >= 1. for r in runs.values()):
                break
    done = dict(manifest=identity, audit=sha(audited), blocks=hashes)
    require(completed is None or completed == done, 'Completion evidence changed')
    report(out, manifest, groups, audits, blocked)
    seal(done_path, done)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke', 'fresh-smoke'), default='full')
    parser.add_argument('--data-dir', type=Path, default=ROOT/'experiments/stl10_transfer/data/stl10_binary')
    parser.add_argument('--confirmation', type=Path, help='Completed historical E42 source')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--capture', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--worker', nargs=4, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    default = 'snapshot_routing_confirmation_full' if opts.preset == 'full' else 'snapshot_routing_confirmation_release_smoke'
    confirmation = (opts.confirmation or ROOT/'outputs'/default).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_paired_boundaries_{opts.preset}').resolve()
    opts.data_dir = opts.data_dir.resolve()
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (confirmation, opts.data_dir)),
            'Output overlaps an input directory')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, confirmation)


if __name__ == '__main__':
    main()
