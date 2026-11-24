"""Compare full D, explicit Demand and shared-schedule Demand on matched STL-10."""

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
from experiments.snapshot_certification_timing.worker import battery, suspend_clock
from experiments.snapshot_graph_scaling.design import cell_id, context_id
from experiments.snapshot_graph_scaling.inputs import raw_sha, verify_bank
from ..confirmation.capture import capture_seed
from ..confirmation.run import DATA_FILES, config
from ..full_training.worker import prepare_snapshot
from ..on_demand.run import path_for
from ..on_demand.worker import student_trace
from ..paired_boundaries.run import check_or_seal, reference
from ..report import eligible
from .design import HEAD_MARGIN_PCT, MIN_WINS, schedule
from .report import report
from .worker import EXPLICIT, METHODS, SHARED, run, shared_accounting

PACKAGE = Path(__file__).resolve().parent
MODULE = 'snapshot_routing.shared_schedule_demand.run'


def worker(opts, manifest, identity):
    out, confirmation = opts.output, opts.confirmation
    protocol = manifest['protocol']
    require(manifest['preset'] == opts.preset and manifest['confirmation'] == str(confirmation)
            and manifest['data_dir'] == str(opts.data_dir) and environment() == manifest['environment']
            and sources() == manifest['dependencies']
            and all(sha(ROOT/path) == digest for path, digest in manifest['code'].items()),
            'Worker context changed')
    if opts.capture is not None:
        fresh = out/'fresh'
        fresh.mkdir(exist_ok=True)
        cases = [c for c in manifest['fresh'] if c['seed'] == opts.capture]
        pending = {cell_id(c) for c in cases if not receipt(fresh/'traces'/f'{cell_id(c)}.json').is_file()}
        require(pending, 'No pending fresh trace')
        capture_seed(fresh, config(protocol, opts.capture), cases, opts.data_dir,
                     manifest['raw_data'], identity, pending)
        return

    index, method, repeat, attempt = opts.worker
    case = manifest['cases'][int(index)]
    repeat, attempt = int(repeat), int(attempt)
    require(method in METHODS or (not repeat and method == 'B'), 'Unknown training path')
    source, payload, ref = reference(out, confirmation, case, manifest, identity)
    prep = out/'preparation'/f'{context_id(case)}.json'
    common = sealed(out/'inputs.json')
    cell = cell_id(case)
    bank = source/'banks'/f'{case["seed"]}.json'
    require(common['manifest'] == identity and sha(bank) == common['banks'][cell]
            and sha(payload.with_suffix('.json')) == common['traces'][cell]
            and sealed(prep)['manifest'] == identity, 'Changed inputs or encoder selection')
    if repeat:
        require(sealed(out/'audited.json')['manifest'] == identity, 'Timing requires a completed audit')
    baseline = sealed(path_for(out, case, 'B')) if method in (EXPLICIT, SHARED) else None
    require(baseline is None or baseline['manifest'] == identity, 'Wrong B audit')
    result = run(source, ref, config(protocol, case['seed']), prep, sealed(bank), method, baseline, audit=not repeat)
    seal(path_for(out, case, method, repeat, attempt),
         dict(manifest=identity, case=case, method=method, repeat=repeat, attempt=attempt, **result))


def read_run(out, case, cfg, identity, method, repeat=0, attempt=0):
    path = path_for(out, case, method, repeat, attempt)
    run = sealed(path)
    require((run['manifest'], run['case'], run['method'], run['repeat'], run['attempt'])
            == (identity, case, method, repeat, attempt) and len(run['observed']) == cfg['rounds'],
            f'Unexpected run: {path}')
    if repeat:
        require(run['comparisons'] == 0 and not run.get('schedule_diagnostics') and not run['evaluations']
                and run['setup_seconds'] > 0
                and [r['round'] for r in run['timing']] == list(range(1, cfg['rounds']+1)),
                f'Incomplete timing: {path}')
    else:
        clients = len(cfg['widths'])
        demand = method in (EXPLICIT, SHARED)
        expected = sum(row['edges'] for row in run['scope']) if demand else cfg['rounds']*(case['public_size']//2)
        require(run['comparisons'] == expected*clients and [r['round'] for r in run['evaluations']] == checkpoints(cfg),
                f'Incomplete audit: {path}')
        if method == SHARED:
            rows = run['schedule_diagnostics']
            expected_trace = [(row['round'], i, row['edges'], clients-1)
                              for row in run['scope'] for i in range(clients)]
            require([(r['round'], r['client'], r['edges'], r['peer_orders']) for r in rows] == expected_trace,
                    f'Incomplete per-client schedule audit: {path}')
    return path, run


def execute(opts):
    out, confirmation = opts.output, opts.confirmation
    marker = out/'manifest.json'
    if opts.worker or opts.capture is not None:
        worker(opts, read(marker), sha(marker))
        return
    cases, fresh, blocks = schedule(opts.preset)
    full = opts.preset == 'full'
    require(not full or (battery() is True and suspend_clock() is not None),
            'Full timing requires observable AC power and suspend time')
    historical, historical_manifest, raw = {}, None, {}
    if full:
        path = confirmation/'manifest.json'
        historical_manifest = sha(path)
        prior = sealed(confirmation/'completed.json')
        e42 = read(path)
        require(prior['manifest'] == historical_manifest and e42['preset'] == 'full',
                'Provide a completed full E42 directory using --confirmation')
        historical = {cell_id(c): prior['traces'][cell_id(c)] for c in cases if c not in fresh}
        print('Checking STL-10 input hashes', flush=True)
        raw = {name: raw_sha(opts.data_dir/name) for name in DATA_FILES}
        require(raw == e42['raw_data'], 'STL-10 files differ from E42')
    shared = ('confirmation/capture.py', 'confirmation/run.py', 'full_training/worker.py',
              'on_demand/engine.py', 'on_demand/protocol.py', 'on_demand/run.py', 'on_demand/worker.py',
              'on_demand/report.py', 'paired_boundaries/run.py', 'paired_boundaries/design.py', 'report.py')
    paths = [*PACKAGE.glob('*.py'), PACKAGE/'README.md', *(PACKAGE.parent/p for p in shared)]
    manifest = dict(preset=opts.preset, protocol=opts.preset, cases=cases, fresh=fresh, blocks=blocks,
                    historical_manifest=historical_manifest, historical_traces=historical,
                    confirmation=str(confirmation), raw_data=raw, data_dir=str(opts.data_dir),
                    environment=environment(), dependencies=sources(), head_margin_pct=HEAD_MARGIN_PCT,
                    minimum_wins=MIN_WINS,
                    code={p.relative_to(ROOT).as_posix(): sha(p) for p in paths})
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

    refs, blocked, traces, banks = {}, {}, {}, {}
    for case in cases:
        cell = cell_id(case)
        source, payload, ref = reference(out, confirmation, case, manifest, identity)
        traces[cell] = sha(payload.with_suffix('.json'))
        if ref['status'] == 'initialization_blocked':
            blocked[cell] = ref['blocked_clients']
            continue
        require(raw_sha(payload) == ref['payload_sha256'], f'Changed teacher trace: {cell}')
        bank = source/'banks'/f'{case["seed"]}.json'
        bank_hash = sha(bank)
        if bank_hash not in banks.values():
            verify_bank(bank)
        banks[cell], refs[cell] = bank_hash, (source, ref)
    inputs = out/'inputs.json'
    check_or_seal(inputs, dict(manifest=identity, traces=traces, banks=banks, blocked=blocked), completed)

    audits, hashes, indices = {}, {}, {cell_id(c): i for i, c in enumerate(cases)}
    for case in cases:
        cell = cell_id(case)
        if cell in blocked:
            continue
        source, ref = refs[cell]
        prep = out/'preparation'/f'{context_id(case)}.json'
        if not receipt(prep).is_file():
            require(completed is None, 'Completed run lost a model snapshot')
            prepare_snapshot(source, ref, config(opts.preset, case['seed']), prep, identity)
        header = sealed(prep)
        require(header['manifest'] == identity and sha(prep.with_suffix('.pt')) == header['model_sha'],
                'Wrong selected encoder')
        hashes[prep.relative_to(out).as_posix()] = sha(prep)
        for method in ('B', *METHODS):
            path = path_for(out, case, method)
            if not receipt(path).is_file():
                require(completed is None, 'Completed run lost its audit')
                print(f'Audit {cell} {method}', flush=True)
                launch('--worker', str(indices[cell]), method, '0', '0')
            path, audit = read_run(out, case, ref['cfg'], identity, method)
            audits[cell, method] = audit
            b = audits[cell, 'B']
            require(b['evaluations'] == audit['evaluations'], f'Audit quality changed: {cell}')
            if method == 'D':
                require(audit['observed'] == b['observed'] and audit['traffic'] == b['traffic'],
                        f'{cell}: D differs from full B')
            if method in (EXPLICIT, SHARED):
                require([student_trace(r) for r in audit['observed']] == [student_trace(r) for r in b['observed']],
                        f'{cell}: Demand changed student targets or trajectory')
            if method == SHARED:
                explicit = audits[cell, EXPLICIT]
                require(all(audit[key] == explicit[key] for key in ('scope', 'observed', 'comparisons')),
                        f'{cell}: shared schedule changed requests, votes or counts')
                shared_accounting(explicit, audit)
            hashes[path.relative_to(out).as_posix()] = sha(path)
    audited = out/'audited.json'
    check_or_seal(audited, dict(manifest=identity, inputs=sha(inputs), hashes=hashes), completed)

    groups, hashes = [], {}
    for block in blocks:
        case, repeat = block['case'], block['repeat']
        cell = cell_id(case)
        if cell in blocked:
            continue
        for attempt in range(2):
            path = out/'blocks'/f'{cell}_r{repeat}_a{attempt}.json'
            exists = receipt(path).is_file()
            require(exists or completed is None, 'Completed run lost a timing block')
            runs, run_hashes = {}, {}
            for method in block['order']:
                if not exists:
                    print(f'{cell} repeat={repeat} attempt={attempt} {method}', flush=True)
                    launch('--worker', str(indices[cell]), method, str(repeat), str(attempt))
                raw_path, result = read_run(out, case, refs[cell][1]['cfg'], identity, method, repeat, attempt)
                audit = audits[cell, method]
                fields = ('observed', 'traffic', 'scope', 'setup_traffic', 'traffic_breakdown') if method != 'D' else (
                    'observed', 'traffic')
                require(all(result[k] == audit[k] for k in fields), f'Timed path differs from audit: {raw_path}')
                if method != 'D':
                    require([r['endpoints'] for r in result['timing']] == [r['endpoints'] for r in audit['scope']],
                            f'Timed endpoint counts differ from audit: {raw_path}')
                run_hashes[method] = sha(raw_path)
                runs[method] = {k: v for k, v in result.items() if k != 'observed'}
            clean = eligible(runs, opts.preset)
            check_or_seal(path, dict(manifest=identity, block=block, attempt=attempt, eligible=clean, runs=run_hashes),
                          completed)
            hashes[path.relative_to(out).as_posix()] = sha(path)
            groups.append((block, attempt, clean, runs))
            if clean:
                break
    files, complete = report(out, manifest, groups, audits, blocked)
    check_or_seal(done_path, dict(manifest=identity, audit=sha(audited), blocks=hashes,
                                  reports=files, eligible_complete=complete), completed)
    print(f'Report: {out/"report.md"}', flush=True)
    require(complete, 'Some configurations have incomplete evidence. See the report.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--confirmation', type=Path, default=ROOT/'outputs/snapshot_routing_confirmation_full')
    parser.add_argument('--data-dir', type=Path, default=ROOT/'experiments/stl10_transfer/data/stl10_binary')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--capture', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--worker', nargs=4, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    opts.confirmation, opts.data_dir = opts.confirmation.resolve(), opts.data_dir.resolve()
    opts.output = (opts.output or ROOT/'outputs'/f'snapshot_routing_shared_schedule_demand_{opts.preset}').resolve()
    require(not any(opts.output.is_relative_to(p) or p.is_relative_to(opts.output)
                    for p in (opts.confirmation, opts.data_dir)), 'Output overlaps input')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts)


if __name__ == '__main__':
    main()
