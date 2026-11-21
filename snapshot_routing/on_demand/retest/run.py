"""Replace only the three power-affected Demand timing quartets."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

for var in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[var] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import (
    ROOT, environment, read, receipt, require, seal, sealed, sha, sources, write,
)
from experiments.snapshot_certification_timing.worker import battery
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import verify_bank

from ...confirmation.run import config
from ...full_training import worker as full_worker
from ...report import eligible, write_csv
from ..report import metrics, report
from ..run import METHODS, anchored, path_for, schedule
from ..worker import run as demand_run

PACKAGE = Path(__file__).resolve().parent
TARGETS = (('dirichlet_0.1', 1), ('dirichlet_0.1', 2), ('iid', 2))
MAX_ATTEMPTS = 2


def validate_timing(run, audit, identity, group, method, attempt):
    require((run['manifest'], run['case'], run['method'], run['repeat'], run['attempt']) ==
            (identity, group['case'], method, group['repeat'], attempt) and run['comparisons'] == 0 and
            len(run['timing']) == len(audit['observed']) and run['setup_seconds'] > 0,
            'Invalid or incomplete timing')
    require(run['observed'] == audit['observed'] and run['traffic'] == audit['traffic'],
            'Retimed method changed its audited training trajectory or communication')
    if method == 'Demand':
        require(run['scope'] == audit['scope'] and run['traffic_breakdown'] == audit['traffic_breakdown'],
                'Demand scope or message byte count changed')


def original_records(source, confirmation, preset):
    m = read(source/'manifest.json')
    done = sealed(source/'completed.json')
    audited = sealed(source/'audited.json')
    identity = sha(source/'manifest.json')
    cases, groups = schedule(preset)
    require(m['preset'] == preset and m['cases'] == cases and m['groups'] == groups and
            done['manifest'] == audited['manifest'] == identity and done['audit'] == sha(source/'audited.json'),
            'The original experiment is incomplete or uses a different schedule')
    require(m['environment'] == environment() and m['dependencies'] == sources() and
            m['package'] == {p.name: sha(p) for p in PACKAGE.parent.glob('*.py')} and
            all(sha(PACKAGE.parents[1]/p) == h for p, h in m['reused'].items()) and
            m['design_sha256'] == sha(PACKAGE.parent/'README.md'),
            'Source code or machine settings differ from the original experiment')
    prior = sealed(confirmation/'completed.json')
    require(prior['manifest'] == sha(confirmation/'manifest.json') and
            sha(confirmation/'completed.json') == m['prior_complete'], 'E42 confirmation input changed')
    audits = {}
    for case in cases:
        cell = cell_id(case)
        require(prior['traces'][cell] == m['traces'][cell], 'E42 trace receipt changed')
        anchored(confirmation, case, preset, m['traces'][cell])
        prep = source/'preparation'/f'{cell}.json'
        prepared = sealed(prep)
        require(prepared['manifest'] == identity and prepared['model_sha'] == sha(prep.with_suffix('.pt'))
                and audited['hashes'][prep.relative_to(source).as_posix()] == sha(prep), 'E45 snapshot changed')
        for method in METHODS:
            path = path_for(source, case, method)
            audit = sealed(path)
            require(audit['case'] == case and audit['method'] == method and audit['manifest'] == identity
                    and audit['repeat'] == 0 and audited['hashes'][path.relative_to(source).as_posix()] == sha(path),
                    f'Invalid audit: {path}')
            audits[cell, method] = audit
    for seed, checksum in m['banks'].items():
        bank = confirmation/'banks'/f'{seed}.json'
        verify_bank(bank)
        require(sha(bank) == checksum, 'E42 public bank changed')
    originals, selected = {}, []
    for i, group in enumerate(groups):
        case, repeat = group['case'], group['repeat']
        cell = cell_id(case)
        path = source/'blocks'/f'{cell}_r{repeat}_a0.json'
        record = sealed(path)
        require(record['manifest'] == identity and record['group'] == group and record['attempt'] == 0
                and done['blocks'][path.relative_to(source).as_posix()] == sha(path), 'Original block seal changed')
        records = {}
        for method in group['order']:
            timed = path_for(source, case, method, repeat)
            run = sealed(timed)
            require(record['runs'][timed.relative_to(source).as_posix()] == sha(timed), 'Original timing changed')
            validate_timing(run, audits[cell, method], identity, group, method, 0)
            records[method] = run
        originals[i] = records
        if not eligible(records, preset):
            selected.append(i)
    if preset == 'full':
        require({(groups[i]['case']['partition'], groups[i]['repeat']) for i in selected} == set(TARGETS),
                'The original invalid blocks differ from the three frozen targets')
    else:
        selected = [0]
    return m, identity, originals, audits, selected


def run_one(opts, out, source, confirmation, manifest):
    index, method, attempt = opts.worker
    index, attempt = int(index), int(attempt)
    original = read(source/'manifest.json')
    require(index in manifest['selected'] and 1 <= attempt <= MAX_ATTEMPTS and method in METHODS and
            sha(source/'manifest.json') == manifest['original_manifest'], 'Invalid retest worker slot')
    group = original['groups'][index]
    case = group['case']
    cell = cell_id(case)
    ref, _ = anchored(confirmation, case, opts.preset, original['traces'][cell])
    bank = confirmation/'banks'/f'{case["seed"]}.json'
    require(sha(bank) == original['banks'][str(case['seed'])], 'Bank receipt changed')
    prep = source/'preparation'/f'{cell}.json'
    args = (confirmation, ref, config(opts.preset, case['seed']), prep, sealed(bank))
    if method == 'Demand':
        result = demand_run(*args, sealed(path_for(source, case, 'B')), audit=False)
    else:
        result = full_worker.run(*args, method, audit=False)
    output = path_for(out, case, method, group['repeat'], attempt)
    seal(output, dict(manifest=manifest['original_manifest'], retest_manifest=sha(out/'manifest.json'),
                      case=case, method=method, repeat=group['repeat'], attempt=attempt, **result))


def execute(opts, out, source, confirmation):
    marker = out/'manifest.json'
    if opts.worker:
        m = read(marker)
        require((m['preset'], m['source'], m['confirmation']) ==
                (opts.preset, str(source), str(confirmation)) and m['environment'] == environment(),
                'Retest worker environment or inputs changed')
        run_one(opts, out, source, confirmation, m)
        return
    m, identity, originals, audits, selected = original_records(source, confirmation, opts.preset)
    manifest = dict(preset=opts.preset, original_manifest=identity, source=str(source), confirmation=str(confirmation),
                    original_completed=sha(source/'completed.json'), selected=selected, max_attempts=MAX_ATTEMPTS,
                    environment=environment(), code=sha(Path(__file__)), design=sha(PACKAGE/'README.md'))
    if marker.exists():
        require(opts.resume and read(marker) == manifest, 'Resume requires identical original data and code')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a fresh retest output directory')
        write(marker, manifest)
    retest_id = sha(marker)
    done_path = out/'completed.json'
    previous = sealed(done_path) if receipt(done_path).exists() else None
    hashes, extras, replacements = {}, [], []
    for index in selected:
        group = m['groups'][index]
        case, repeat = group['case'], group['repeat']
        cell = cell_id(case)
        initial_fault = ', '.join(f"{m}: {r['power'].get('battery', 0)} battery sample(s)"
                                  for m, r in originals[index].items() if r['power'].get('battery'))
        for attempt in range(1, MAX_ATTEMPTS+1):
            path = out/'blocks'/f'{cell}_r{repeat}_a{attempt}.json'
            stored = sealed(path) if receipt(path).is_file() else None
            require(stored is not None or previous is None, 'Completed retest lost a block')
            if stored is None and opts.preset == 'full':
                require(battery() is True, 'Connect AC power before starting the next paired block, then use --resume')
            block, run_hashes = {}, {}
            for method in group['order']:
                if stored is None:
                    print(f'{cell} block {repeat} attempt {attempt} {method}', flush=True)
                    subprocess.run([sys.executable, '-B', '-m', 'snapshot_routing.on_demand.retest.run',
                                    '--preset', opts.preset, '--source', str(source), '--confirmation', str(confirmation),
                                    '--output', str(out), '--worker', str(index), method, str(attempt)],
                                   cwd=ROOT, check=True)
                target = path_for(out, case, method, repeat, attempt)
                record = sealed(target)
                require(record['retest_manifest'] == retest_id, 'Retest run identity changed')
                validate_timing(record, audits[cell, method], identity, group, method, attempt)
                run_hashes[target.relative_to(out).as_posix()] = sha(target)
                block[method] = record
            clean = eligible(block, opts.preset)
            payload = dict(manifest=retest_id, group=group, attempt=attempt, accepted=clean, runs=run_hashes)
            if stored is None:
                seal(path, payload)
            else:
                require(stored == payload, 'Retest block seal changed')
            hashes[path.relative_to(out).as_posix()] = sha(path)
            extras.extend(block.values())
            for method in group['order']:
                replacements.append(dict(cell=cell, repeat=repeat, attempt=attempt, method=method, accepted=clean,
                                         original_power_flags=initial_fault,
                                         original_seconds=metrics(originals[index][method])['head_seconds'],
                                         retest_seconds=metrics(block[method])['head_seconds'],
                                         battery=block[method]['power'].get('battery', 0),
                                         unknown=block[method]['power'].get('unknown', 0),
                                         suspend_seconds=block[method]['suspend_seconds']))
            if clean:
                break
    completion = dict(manifest=retest_id, original_sha256=manifest['original_completed'], blocks=hashes)
    require(previous is None or previous == completion, 'Retest completion record changed')
    combined = [r for group in originals.values() for r in group.values()] + extras
    report(out, combined, audits, m)
    write_csv(out/'replacements.csv', replacements)
    seal(done_path, completion)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full','smoke'), default='full')
    parser.add_argument('--source', type=Path, help='Original completed on-demand experiment')
    parser.add_argument('--confirmation', type=Path, help='E42 input directory, inferred from the original manifest')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', nargs=3, help=argparse.SUPPRESS)
    opts = parser.parse_args()
    name = ('snapshot_routing_on_demand_full' if opts.preset == 'full'
            else 'snapshot_routing_on_demand_verified_smoke')
    source = (opts.source or ROOT/'outputs'/name).resolve()
    confirmation = (opts.confirmation or Path(read(source/'manifest.json')['confirmation'])).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_on_demand_retest_{opts.preset}').resolve()
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (source, confirmation)),
            'Output overlaps original evidence')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, source, confirmation)


if __name__ == '__main__':
    main()
