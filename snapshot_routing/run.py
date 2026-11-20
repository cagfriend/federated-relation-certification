"""Map the net-cost boundary of local exact relation routing on E40 traces."""

import argparse
import os
from pathlib import Path
import subprocess
import sys

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import numpy as np
import torch
from threadpoolctl import threadpool_limits

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.timing import difference
from experiments.private_corrected_guard.run import digest
from experiments.public_scaling.certification import hard_relations
from experiments.snapshot_certification_timing.design import (ROOT, environment, history_pair, read, receipt,
                                                                require, seal, sealed, sha, sources, write)
from experiments.snapshot_certification_timing.engine import Engine
from experiments.snapshot_graph_scaling.design import cell_id, context_id, run_path
from experiments.snapshot_graph_scaling.inputs import load_bank, raw_sha, selected_models, verify_bank

from .replay import METHODS, POLICY, replay
from .report import build, fit, repeats

PACKAGE = ROOT/'snapshot_routing'


def inputs(source, preset):
    manifest = read(source/'manifest.json')
    bank_lock = sealed(source/'banks_sealed.json')
    audit = sealed(source/'audit_passed.json')
    done = sealed(source/'completed.json')
    identity = sha(source/'manifest.json')
    require(manifest['preset'] == preset and bank_lock['manifest_sha256'] == audit['manifest_sha256']
            == done['manifest_sha256'] == identity and done['audit_sha256'] == sha(source/'audit_passed.json'),
            'E40 source is incomplete or uses another preset')
    cases = [c for c in manifest['schedule'] if c['method'] == 'B' and c['stage'] == 'audit']
    require(len(cases) == (12 if preset == 'full' else 3) and
            len({cell_id(c) for c in cases}) == len(cases), 'Invalid E40 B audit matrix')
    return manifest, cases, dict(audit=audit['hashes'], banks=bank_lock['banks'], manifest=identity)


def capture(source, manifest, lock, case, destination):
    anchor_path = source/run_path(case)
    require(sha(anchor_path) == lock['audit'][run_path(case)], 'E40 audit changed')
    anchor = sealed(anchor_path)
    require(anchor['case'] == case and anchor['manifest_sha256'] == lock['manifest'], 'E40 audit identity changed')
    seed, part = case['seed'], case['partition']
    history = Path(manifest['history_root'])
    cache = Path(manifest['cache'])/str(seed)
    prep_dir = Path(manifest['reference_root'])/'preparation'
    cid = context_id(case)
    require(sha(prep_dir/f'{cid}.json') == manifest['preparation'][cid], 'E40 selected encoder record changed')
    cfg = anchor['cfg']
    base = read(history/'manifest.json')['configs'][str(seed)]
    old, anchors = history_pair(history, base, part)
    require(anchors == manifest['history'][cid], 'E38 reference changed')
    models, train, _, _ = selected_models(prep_dir, case, base, cache, old, anchors)
    bank_path = source/'banks'/f'{seed}.json'
    require(sha(bank_path) == lock['banks'][str(seed)], 'E40 public bank record changed')
    bank = verify_bank(bank_path)
    public, ids = load_bank(source, case, train, bank)

    torch.manual_seed(seed)
    np.random.seed(seed)
    engine = Engine(models, cfg, Wire(), train['private'], public.clone(), method='B', initialization='centers',
                    strength=.5, until=cfg['rounds'], all_clients=True)
    initial = dict(model_digest=model_digest(models), head_digest=engine.state_digest(),
                   graph_digest=digest(engine.edges), public_ids_digest=digest(ids.numpy()),
                   centers=[digest(x) for x in engine.centers], pseudo=[digest(y) for y in engine.pseudo],
                   setup_traffic=engine.traffic())
    require(initial == anchor['initial'], 'Capture initialized a different E40 model or graph')
    features = dict((f'x{i}', x) for i, x in enumerate(engine.public))
    heads = [[] for _ in engine.heads]
    packed = []
    previous = engine.traffic()
    for rnd, row in enumerate(anchor['rows'], 1):
        stat = engine.round(train['private'], public, seed, rnd)
        relations, snapshot = engine.last_relations, engine.last_snapshot
        checks = dict(round=rnd, head_digest=engine.state_digest(),
                      teacher_by_client=[[digest(w), digest(b)] for w, b in snapshot],
                      relations=[digest(x) for x in relations], aggregate=digest(engine.protocol.counts),
                      targets_used=[digest(t[o]) for t, o in zip(stat['consumed'], stat['public_orders'])],
                      student_orders=[digest(o) for o in stat['public_orders']],
                      private_losses=stat['private_losses'], public_losses=stat['public_losses'],
                      traffic_delta=difference(engine.traffic(), previous))
        require(all(row[k] == v for k, v in checks.items()), f'E40 trajectory identity changed at round {rnd}')
        for c, ((w, b), x, rel) in enumerate(zip(snapshot, engine.public, relations)):
            require(np.array_equal(rel, hard_relations((x @ w.T + b).argmax(1), engine.edges)),
                    f'Oracle mismatch on capture at client {c}, round {rnd}')
            heads[c].append((w, b))
        packed.append([np.packbits(rel) for rel in relations])
        previous = engine.traffic()
    require(len(packed) == cfg['rounds'] and previous == anchor['traffic'] and
            model_digest(models) == initial['model_digest'], 'E40 capture is incomplete')
    arrays = {f'{key}{i}': np.stack([pair[j] for pair in snapshots])
              for i, snapshots in enumerate(heads) for j, key in enumerate(('w', 'b'))}
    with destination.open('wb') as f:
        np.savez(f, edges=engine.edges, relations=np.asarray(packed), **features, **arrays)


def paths(out, cases, preset):
    n = repeats(preset)
    # Rotate cell order and method positions. Relative order within each stage is varied too.
    for stage, methods in [('fixed', METHODS[:3]), ('routing', METHODS[3:])]:
        for rep in range(n):
            for offset in range(len(cases)):
                i = (offset+rep) % len(cases)
                cell = cell_id(cases[i])
                order = (rep+i) % len(methods)
                for method in methods[order:]+methods[:order]:
                    yield stage, cell, method, rep+1, out/stage/f'{cell}_{method}_r{rep+1}.json'


def worker(opts, out, source, manifest, lock, cases):
    run_manifest = read(out/'manifest.json')
    identity = sha(out/'manifest.json')
    require(run_manifest['source'] == str(source) and run_manifest['inputs'] == lock and
            run_manifest['environment'] == environment(), 'Worker inputs or environment changed')
    if opts.capture:
        case = next(c for c in cases if cell_id(c) == opts.capture)
        path = out/'traces'/f'{opts.capture}.npz'
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.part')
        capture(source, manifest, lock, case, temporary)
        temporary.replace(path)
        seal(path.with_suffix('.json'), dict(manifest=identity, payload_sha256=raw_sha(path)))
        return
    stage, cell, method, repeat, output = list(paths(out, cases, opts.preset))[opts.worker]
    path = out/'traces'/f'{cell}.npz'
    record = sealed(path.with_suffix('.json'))
    require(record['manifest'] == identity and record['payload_sha256'] == raw_sha(path),
            'Replay trace identity changed')
    rules = {}
    rule_sha = None
    if stage == 'routing':
        rule_path = out/'rules.json'
        rule_record = sealed(rule_path)
        require(rule_record['manifest'] == identity, 'Routing rule was fit to another run')
        rules, rule_sha = rule_record['tables'][cell], sha(rule_path)
    with np.load(path, allow_pickle=False) as trace:
        result = replay(method, trace, rules, opts.preset == 'smoke')
    seal(output, dict(manifest=identity, trace_sha=record['payload_sha256'], rule_sha=rule_sha,
                      cell=cell, method=method, repeat=repeat, **result))


def execute(opts, out, source):
    manifest, cases, lock = inputs(source, opts.preset)
    if opts.worker is not None or opts.capture:
        worker(opts, out, source, manifest, lock, cases)
        return
    record = dict(preset=opts.preset, source=str(source), inputs=lock, environment=environment(),
                  policy=POLICY, dependencies=sources(),
                  package={p.name: sha(p) for p in sorted(PACKAGE.glob('*.py'))},
                  design=sha(PACKAGE/'README.md'))
    marker = out/'manifest.json'
    if marker.exists():
        require(opts.resume and read(marker) == record, 'Resume requires identical inputs and code')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use a fresh output directory')
        write(marker, record)
    identity = sha(marker)

    def launch(*arg):
        subprocess.run([sys.executable, '-B', '-m', 'snapshot_routing.run', '--preset', opts.preset,
                        '--source', str(source), '--output', str(out), *arg], cwd=ROOT, check=True)

    traces, anchors = {}, {}
    for case in cases:
        cell = cell_id(case)
        path = out/'traces'/f'{cell}.npz'
        header = path.with_suffix('.json')
        if not receipt(header).is_file():
            print(f'Capturing and checking B trajectory: {cell}', flush=True)
            launch('--capture', cell)
        traces[cell] = sealed(header)
        require(traces[cell]['manifest'] == identity and traces[cell]['payload_sha256'] == raw_sha(path),
                'Captured trace changed')
        anchors[cell] = sealed(source/run_path(case))['cfg']

    runs, hashes = [], {}
    rule_path = out/'rules.json'
    rule_sha = None
    jobs = list(paths(out, cases, opts.preset))
    for i, (stage, cell, method, repeat, path) in enumerate(jobs):
        if stage == 'routing' and rule_sha is None:
            tables = fit(cases, anchors, runs, opts.preset)
            rules = dict(manifest=identity, fixed_inputs=dict(hashes), tables=tables)
            if receipt(rule_path).is_file():
                require(sealed(rule_path) == rules, 'Frozen rules or fitting runs changed')
            else:
                seal(rule_path, rules)
            rule_sha = sha(rule_path)
        if not receipt(path).is_file():
            print(f'{i+1}/{len(jobs)} {cell} {method} repeat={repeat}', flush=True)
            launch('--worker', str(i))
        data = sealed(path)
        cfg = anchors[cell]
        require((data['manifest'], data['cell'], data['method'], data['repeat'], data['trace_sha'], data['rule_sha'])
                == (identity, cell, method, repeat, traces[cell]['payload_sha256'], rule_sha) and
                len(data['rows']) == cfg['rounds'] and
                data['comparisons'] == cfg['rounds']*len(cfg['widths'])*cfg['public_size']//2,
                f'Incomplete or mismatched replay: {path}')
        runs.append(data)
        hashes[str(path.relative_to(out))] = sha(path)
    done = dict(manifest=identity, hashes=hashes, rule_sha=rule_sha,
                traces={cell: trace['payload_sha256'] for cell, trace in traces.items()})
    completed = out/'completed.json'
    if receipt(completed).is_file():
        require(sealed(completed) == done, 'Completed evidence changed')
    build(out, cases, anchors, runs, opts.preset)
    seal(completed, done)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('smoke', 'full'), default='full')
    parser.add_argument('--source', type=Path, help='Completed E40 graph scaling directory')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    parser.add_argument('--capture', help=argparse.SUPPRESS)
    opts = parser.parse_args()
    default_source = (ROOT/'experiments/snapshot_graph_scaling/results_full' if opts.preset == 'full'
                      else ROOT/'outputs/snapshot_graph_scaling_smoke')
    source = (opts.source or default_source).resolve()
    out = (opts.output or ROOT/'outputs'/f'snapshot_routing_{opts.preset}').resolve()
    require(not (out.is_relative_to(source) or source.is_relative_to(out)), 'Output overlaps the E40 input')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(opts, out, source)


if __name__ == '__main__':
    main()
