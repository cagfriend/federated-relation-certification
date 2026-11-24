"""Retime the three paths on the completed shared-schedule experiment's inputs."""

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
    ROOT, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_certification_timing.worker import battery, suspend_clock
from experiments.snapshot_graph_scaling.design import cell_id, context_id
from experiments.snapshot_graph_scaling.inputs import raw_sha, verify_bank
from ..confirmation.run import config
from ..on_demand.run import path_for
from ..on_demand.worker import student_trace
from ..paired_boundaries.run import check_or_seal, reference
from ..report import eligible
from ..shared_schedule_demand.design import HEAD_MARGIN_PCT, MIN_WINS, schedule
from ..shared_schedule_demand.run import read_run as read_prior_run
from ..shared_schedule_demand.worker import SHARED
from .report import report
from .worker import EXPLICIT, LEADER, METHODS, leader_accounting, run

PACKAGE = Path(__file__).resolve().parent
MODULE = 'snapshot_routing.leader_schedule_demand.run'


def source_records(root, preset):
    marker = root/'manifest.json'
    old = read(marker)
    identity = sha(marker)
    done = sealed(root/'completed.json')
    require(done['manifest'] == identity and done['eligible_complete'] and old['preset'] == preset
            and old['protocol'] == preset and old['dependencies'] == sources()
            and all(sha(ROOT/path) == digest for path, digest in old['code'].items()),
            'Need a completed shared-schedule experiment with matching workload and code')
    audited = root/'audited.json'
    inputs = root/'inputs.json'
    provenance = sealed(audited)
    setup = sealed(inputs)
    require(sha(audited) == done['audit'] and provenance['manifest'] == identity
            and sha(inputs) == provenance['inputs'] and setup['manifest'] == identity and not setup['blocked'],
            'Previous audits or prepared inputs did not pass')
    cases, fresh, blocks = schedule(preset)
    require((old['cases'], old['fresh'], old['blocks']) == (cases, fresh, blocks),
            'Previous workload differs from the frozen comparison')
    return old, identity, setup, provenance['hashes']


def cell_inputs(root, old, anchor, common, hashes, case):
    cell = cell_id(case)
    source, payload, ref = reference(root, Path(old['confirmation']), case, old, anchor)
    prep = root/'preparation'/f'{context_id(case)}.json'
    bank = source/'banks'/f'{case["seed"]}.json'
    header = sealed(prep)
    require(ref['status'] == 'captured' and sha(payload.with_suffix('.json')) == common['traces'][cell]
            and sha(bank) == common['banks'][cell] and header['manifest'] == anchor
            and sha(prep) == hashes[prep.relative_to(root).as_posix()], f'Changed inputs: {cell}')
    return source, payload, ref, prep, bank


def prior_audit(root, case, cfg, anchor, hashes, method):
    path, result = read_prior_run(root, case, cfg, anchor, method)
    require(sha(path) == hashes[path.relative_to(root).as_posix()], f'Changed prior audit: {path}')
    return result


def worker(opts, manifest, identity):
    root = opts.source
    old, anchor, common, hashes = source_records(root, opts.preset)
    require(manifest['source'] == str(root) and anchor == manifest['source_manifest']
            and sha(root/'completed.json') == manifest['source_completed']
            and environment() == manifest['environment']
            and all(sha(ROOT/path) == digest for path, digest in manifest['code'].items()),
            'Worker context changed')
    index, method, repeat, attempt = opts.worker
    case = manifest['cases'][int(index)]
    repeat, attempt = int(repeat), int(attempt)
    require(method in METHODS and (repeat or method == LEADER), 'Wrong path')
    source, _, ref, prep, bank = cell_inputs(root, old, anchor, common, hashes, case)
    if repeat:
        require(sealed(opts.output/'audited.json')['manifest'] == identity, 'Timing requires passed audit')
    baseline = prior_audit(root, case, ref['cfg'], anchor, hashes, 'B') if method != 'D' else None
    result = run(source, ref, config(opts.preset, case['seed']), prep, sealed(bank), method, baseline,
                 audit=not repeat)
    seal(path_for(opts.output, case, method, repeat, attempt),
         dict(manifest=identity, case=case, method=method, repeat=repeat, attempt=attempt, **result))


def load_run(out, case, identity, method, repeat=0, attempt=0):
    path = path_for(out, case, method, repeat, attempt)
    record = sealed(path)
    require((record['manifest'], record['case'], record['method'], record['repeat'], record['attempt'])
            == (identity, case, method, repeat, attempt), f'Unexpected run: {path}')
    return path, record


def check_audit(case, cfg, audit, b, explicit):
    cell = cell_id(case)
    rows = audit['schedule_diagnostics']
    clients = len(cfg['widths'])
    expected = [(r['round'], 0, clients-1, r['edges']) for r in explicit['scope']]
    require([(r['round'], r['client'], r['peer_orders'], r['edges']) for r in rows] == expected,
            f'{cell}: incomplete leader reconstruction audit')
    require(all(audit[key] == explicit[key] for key in ('observed', 'scope', 'comparisons', 'evaluations'))
            and [student_trace(row) for row in audit['observed']] == [student_trace(row) for row in b['observed']],
            f'{cell}: changed Demand relation or student trajectory')
    leader_accounting(explicit, audit)


def check_timing(timed, audit, cfg):
    method = timed['method']
    fields = ('observed', 'traffic') if method == 'D' else (
        'observed', 'traffic', 'scope', 'traffic_breakdown', 'setup_traffic')
    require(timed['setup_seconds'] > 0 and not timed['comparisons'] and not timed['evaluations']
            and not timed.get('schedule_diagnostics') and all(timed[k] == audit[k] for k in fields)
            and [r['round'] for r in timed['timing']] == list(range(1, cfg['rounds']+1)),
            f'{method}: timed path differs from independent audit')
    if method != 'D':
        require([r['endpoints'] for r in timed['timing']] == [r['endpoints'] for r in audit['scope']],
                f'{method}: endpoint work changed')


def execute(opts):
    out, root = opts.output, opts.source
    marker = out/'manifest.json'
    if opts.worker:
        worker(opts, read(marker), sha(marker))
        return
    require(opts.preset == 'smoke' or (battery() is True and suspend_clock() is not None),
            'Full timing requires observable AC power and suspend time')
    old, anchor, common, hashes = source_records(root, opts.preset)
    require(not out.is_relative_to(Path(old['confirmation'])) and not out.is_relative_to(Path(old['data_dir'])),
            'Output overlaps original inputs')
    cases = old['cases']
    blocks = [{**b, 'order': [LEADER if m == SHARED else m for m in b['order']]} for b in old['blocks']]
    code = {p.relative_to(ROOT).as_posix(): sha(p)
            for p in [*sorted(PACKAGE.glob('*.py')), PACKAGE/'README.md']}
    manifest = dict(preset=opts.preset, source=str(root), source_manifest=anchor,
                    source_completed=sha(root/'completed.json'), cases=cases, blocks=blocks,
                    environment=environment(), head_margin_pct=HEAD_MARGIN_PCT, minimum_wins=MIN_WINS, code=code)
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical source, code and environment')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a new output directory')
        write(marker, manifest)
    identity = sha(marker)
    done = out/'completed.json'
    completed = sealed(done) if receipt(done).is_file() else None

    def launch(index, method, repeat=0, attempt=0):
        print(f'{cell_id(cases[index])} {method} block={repeat} attempt={attempt}', flush=True)
        subprocess.run([sys.executable, '-B', '-m', MODULE, '--preset', opts.preset, '--source', str(root),
                        '--output', str(out), '--worker', str(index), method, str(repeat), str(attempt)],
                       cwd=ROOT, check=True)

    audited = out/'audited.json'
    audits, local_hashes, cfgs, banks = {}, {}, {}, set()
    for i, case in enumerate(cases):
        cell = cell_id(case)
        _, payload, ref, prep, bank = cell_inputs(root, old, anchor, common, hashes, case)
        require(raw_sha(payload) == ref['payload_sha256']
                and sha(prep.with_suffix('.pt')) == sealed(prep)['model_sha'], f'Changed teacher or encoder: {cell}')
        if bank not in banks:
            verify_bank(bank)
            banks.add(bank)
        cfgs[cell] = ref['cfg']
        audits[cell] = {m: prior_audit(root, case, ref['cfg'], anchor, hashes, m) for m in ('B', 'D', EXPLICIT)}
        if not receipt(path_for(out, case, LEADER)).is_file():
            require(completed is None, 'Completed experiment lost an audit')
            launch(i, LEADER)
        path, new = load_run(out, case, identity, LEADER)
        check_audit(case, ref['cfg'], new, audits[cell]['B'], audits[cell][EXPLICIT])
        audits[cell][LEADER] = new
        local_hashes[path.relative_to(out).as_posix()] = sha(path)
    check_or_seal(audited, dict(manifest=identity, source_audited=sha(root/'audited.json'), runs=local_hashes),
                  completed)

    groups, block_hashes = [], {}
    for block in blocks:
        case, repeat = block['case'], block['repeat']
        cell = cell_id(case)
        for attempt in range(2):
            path = out/'blocks'/f'{cell}_r{repeat}_a{attempt}.json'
            exists = receipt(path).is_file()
            require(exists or completed is None, 'Completed experiment lost a timing block')
            runs, run_hashes = {}, {}
            for method in block['order']:
                if not exists:
                    launch(cases.index(case), method, repeat, attempt)
                raw, result = load_run(out, case, identity, method, repeat, attempt)
                check_timing(result, audits[cell][method], cfgs[cell])
                run_hashes[method] = sha(raw)
                runs[method] = {k: v for k, v in result.items() if k != 'observed'}
            clean = eligible(runs, opts.preset)
            check_or_seal(path, dict(manifest=identity, block=block, attempt=attempt, eligible=clean, runs=run_hashes),
                          completed)
            block_hashes[path.relative_to(out).as_posix()] = sha(path)
            groups.append((block, attempt, clean, runs))
            if clean:
                break
    reports, complete = report(out, manifest, groups, audits)
    check_or_seal(done, dict(manifest=identity, audit=sha(audited), blocks=block_hashes,
                            reports=reports, eligible_complete=complete), completed)
    print(f'Report: {out/"report.md"}', flush=True)
    require(complete, 'Incomplete eligible timing blocks. See the report.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--source', type=Path, help='Completed shared-schedule experiment of the same preset')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=4, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    opts.source = (opts.source or ROOT/'outputs'/f'snapshot_routing_shared_schedule_demand_{opts.preset}').resolve()
    opts.output = (opts.output or ROOT/'outputs'/f'snapshot_routing_leader_schedule_demand_{opts.preset}').resolve()
    require(not (opts.source.is_relative_to(opts.output) or opts.output.is_relative_to(opts.source)),
            'Output overlaps source results')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts)


if __name__ == '__main__':
    main()
