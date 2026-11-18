"""Compare the current snapshot method and isolate the cost of the margin guard."""
import argparse
import os
from pathlib import Path
from statistics import mean
import subprocess
import sys
from time import perf_counter

import numpy as np
import torch
from threadpoolctl import threadpool_limits

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.design import config
from experiments.external_pilot.evaluate import evaluate, scores
from experiments.external_pilot.prepare import load, prepare, read, sha, write
from experiments.external_pilot.run import ROOT, make, sources
from experiments.external_pilot.timing import Ledger, difference, observe
from experiments.private_corrected_guard.engine import CorrectedGuardOurs
from experiments.private_corrected_guard.run import digest
from .selection import select_models


EXTERNAL = ('Hetero-SSFL', 'FLESD', 'FedMKD')
ON, OFF = 'Ours-0.5', 'Ours-0'
FORMAL = ((1201, 'iid'), (1201, 'dirichlet_0.1'), (1207, 'dirichlet_0.1'), (1208, 'iid'))
STAGES = ('compute_seconds', 'serialization_seconds', 'aggregation_seconds', 'other_seconds')


def plan(preset):
    contexts = FORMAL if preset == 'full' else ((1201, 'iid'),)
    jobs = []
    for idx, (seed, partition) in enumerate(contexts):
        # The two paired repeats use opposite order. Rotate external order across cases.
        external = EXTERNAL[idx % len(EXTERNAL):] + EXTERNAL[:idx % len(EXTERNAL)]
        methods = [(ON, 1), (OFF, 1), *((m, 1) for m in external), (OFF, 2), (ON, 2)]
        jobs.extend(dict(seed=seed, partition=partition, method=m, repeat=n) for m, n in methods)
    return jobs


def name(case):
    return '{seed}_{partition}_{method}_r{repeat}.json'.format(**case)


def cfg_for(preset, seed):
    return dict(config('pilot' if preset == 'full' else 'smoke'), seed=seed)


def timed(ledger, wire, operation):
    before = ledger.snapshot()
    with observe(ledger, wire):
        start = perf_counter()
        with ledger.phase('compute_seconds'):
            value = operation()
        elapsed = perf_counter() - start
    phases = difference(ledger.snapshot(), before)
    phases['other_seconds'] = elapsed - sum(phases.values())
    return value, elapsed, {k: phases.get(k, 0.) for k in STAGES}


@torch.no_grad()
def assessment(algorithm, train, evaluation, cfg, test_features):
    common = evaluate(algorithm, train['private'], evaluation, cfg)
    if test_features is not None:
        truth = evaluation['truth'].numpy()
        for c, (row, features, head) in enumerate(zip(common['clients'], test_features, algorithm.heads)):
            # Use the same scoring function on actual raw-head argmax cluster IDs.
            row['native_head'] = scores(truth, (features @ head.w.T + head.b).argmax(1), cfg['classes'])
            count = (algorithm.public[c] @ head.w.T + head.b).argmax(1)
            row['native_public_largest'] = float(np.bincount(count, minlength=cfg['classes']).max() / len(count))
    return common


def worker(out, case, preset):
    cfg = cfg_for(preset, case['seed'])
    part, method = case['partition'], case['method']
    cache = out / 'cache' / str(case['seed'])
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    models, train, meta = load(cache, part, cfg)
    evaluation = torch.load(cache/part/'evaluation.pt', weights_only=True)
    base_hash = model_digest(models)
    wire, ledger = Wire(), Ledger()
    ours = method in (ON, OFF)
    selection_seconds, selection = 0., []
    base = dict(case=case, cfg=cfg, input_files=meta['files'], initial_model_digest=base_hash,
                ae_seconds=meta['common_ae_seconds'], status='completed')
    if ours:
        start = perf_counter()
        models, selection = select_models(cfg, models, train)
        selection_seconds = perf_counter() - start
        if any(r['selected'] is None for r in selection):
            return dict(base, status='initialization_blocked', selection=selection, selection_seconds=selection_seconds)
    # Restore standard training RNG after snapshot replay, which seeds AE modules.
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    if ours:
        def create():
            return CorrectedGuardOurs(models, cfg, wire, train['private'], train['public'],
                                      initialization='centers', strength=.5 if method == ON else 0.,
                                      until=cfg['rounds'], all_clients=True)
    else:
        def create():
            return make(method, models, cfg, wire, train)
    initial = model_digest(models)
    algorithm, setup, setup_parts = timed(ledger, wire, create)
    algorithm.observer = ledger
    test_features = None
    if ours:
        algorithm.protocol.observer = ledger
        for c, (labels, centers, rec) in enumerate(zip(algorithm.pseudo, algorithm.centers, selection)):
            chosen = rec['candidates'][rec['selected']]
            if digest(labels) != chosen['pseudo_digest'] or digest(centers) != chosen['centers_digest']:
                raise ValueError(f'Chosen clusters differ from training initialization for client {c}')
        with torch.no_grad():
            test_features = [m.encode(evaluation['test']).double().numpy() for m in models]

    traffic = algorithm.traffic if ours else wire.snapshot
    rows, observations, audit = [], [], 0
    cumulative = setup
    def check(rnd):
        observations.append(dict(round=rnd, cumulative_method_seconds=cumulative,
                                 cumulative_with_prep_seconds=cumulative+base['ae_seconds']+selection_seconds,
                                 cumulative_bytes=traffic().get('total_bytes', 0),
                                 **assessment(algorithm, train, evaluation, cfg, test_features)))
    check(0)
    previous = traffic()
    for rnd in range(1, cfg['rounds'] + 1):
        stats, elapsed, timing = timed(ledger, wire, lambda: algorithm.round(
            train['private'], train['public'], cfg['seed'], rnd))
        cumulative += elapsed
        total = traffic()
        row = dict(round=rnd, seconds=elapsed, timing=timing, traffic_delta=difference(total, previous))
        previous = total
        if ours:
            guard = stats['guard_clients']
            if len(guard) != len(models) or any(g['active'] != (method == ON) for g in guard):
                raise ValueError('Wrong guard state')
            audit += algorithm.audit()
            row.update(head_digest=algorithm.state_digest(), guard_seconds=sum(g['seconds'] for g in guard),
                       private_seconds=stats['private_seconds'], generation_seconds=stats['generation_seconds'],
                       exchange_seconds=stats['exchange_seconds'], public_seconds=stats['public_seconds'],
                       teacher_positive_rates=[float(r.mean()) for r in algorithm.last_relations],
                       aggregate_positive_rate=float(algorithm.protocol.counts.mean()/len(models)))
        rows.append(row)
        if rnd % cfg['eval_every'] == 0 or rnd == cfg['rounds']:
            check(rnd)
        if rnd % 50 == 0 or rnd == cfg['rounds']:
            print(f'{name(case)} {rnd}/{cfg["rounds"]}', flush=True)
    if ours and (initial != model_digest(models) or audit != cfg['rounds']*len(models)*len(algorithm.edges)):
        raise ValueError('Frozen encoders or relation audit failed')
    return dict(base, selection=selection, selection_seconds=selection_seconds,
                selected_model_digest=initial, setup_seconds=setup, setup_timing=setup_parts,
                method_seconds=cumulative, with_preparation_seconds=cumulative+base['ae_seconds']+selection_seconds,
                rows=rows, evaluations=observations, traffic=traffic(), relation_audits=audit,
                initial_head_sources=None if not ours else [digest(c) for c in algorithm.centers])


def quality(clients):
    result = {k: mean(c[k] for c in clients) for k in ('acc', 'nmi', 'ari', 'largest', 'empty')}
    result.update(worst_acc=min(c['acc'] for c in clients), worst_largest=max(c['largest'] for c in clients),
                  single_clients=sum(c['occupied'] == 1 for c in clients),
                  same_pair_rate=mean(same_pair_rate(c['cluster_counts']) for c in clients))
    return result


def same_pair_rate(counts):
    n = sum(counts)
    return sum(k * (k - 1) for k in counts) / (n * (n - 1))


def equivalent(a, b):
    return (a['selected_model_digest'] == b['selected_model_digest']
            and a['initial_head_sources'] == b['initial_head_sources']
            and a['traffic'] == b['traffic']
            and [r['head_digest'] for r in a['rows']] == [r['head_digest'] for r in b['rows']]
            and [r['clients'] for r in a['evaluations']] == [r['clients'] for r in b['evaluations']])


def final_report(out, entries):
    from .report import write_report
    return write_report(out, entries)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--preset', choices=('full', 'smoke'), default='full')
    p.add_argument('--output', type=Path)
    p.add_argument('--data-dir', type=Path, default=ROOT/'experiments/stl10_transfer/data/stl10_binary')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    args = p.parse_args()
    out = (args.output or ROOT/f'experiments/snapshot_external_comparison/results_{args.preset}').resolve()
    data = args.data_dir.resolve()
    if out.is_relative_to(data) or data.is_relative_to(out):
        p.error('Output overlaps the input data.')
    schedule = plan(args.preset)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    manifest = dict(preset=args.preset, data=str(data) if args.preset == 'full' else None,
                    schedule=schedule, configs={str(c['seed']): cfg_for(args.preset, c['seed']) for c in schedule},
                    sources=sources(), torch=str(torch.__version__), numpy=np.__version__)
    with threadpool_limits(1):
        path = out/'manifest.json'
        if args.worker is not None:
            if read(path) != manifest:
                raise ValueError('Worker configuration or source differs from manifest')
            case = schedule[args.worker]
            result = worker(out, case, args.preset)
            dest = out/'runs'/name(case)
            write(dest, dict(manifest_sha256=sha(path), **result))
            write(dest.with_suffix('.sha256.json'), dict(sha256=sha(dest)))
            return
        if path.exists():
            if not args.resume or manifest != read(path):
                p.error('Existing output requires --resume with the same source and settings.')
        else:
            if out.exists() and (not out.is_dir() or any(out.iterdir())):
                p.error('Output must be new or empty.')
            write(path, manifest)
        entries = []
        for seed in manifest['configs']:
            prepare(out/'cache'/seed, data, manifest['configs'][seed])
        for idx, case in enumerate(schedule):
            dest = out/'runs'/name(case)
            receipt = dest.with_suffix('.sha256.json')
            if not receipt.exists():
                print(f'{idx+1}/{len(schedule)} {dest.name}', flush=True)
                env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1',
                           LOKY_MAX_CPU_COUNT='1')
                cmd = [sys.executable, '-B', '-m', 'experiments.snapshot_external_comparison.run',
                       '--preset', args.preset, '--data-dir', str(data), '--output', str(out), '--worker', str(idx)]
                subprocess.run(cmd, cwd=ROOT, env=env, check=True)
            if not dest.exists() or read(receipt)['sha256'] != sha(dest):
                raise ValueError(f'Run checksum mismatch: {dest}')
            r = read(dest)
            if r['case'] != case or r['manifest_sha256'] != sha(path):
                raise ValueError(f'Run provenance mismatch: {dest}')
            entries.append(r)
        final_report(out, entries)
        write(out/'completed.json', dict(attempts=len(entries), finished=sum(r['status']=='completed' for r in entries),
                                         runs={name(c): sha(out/'runs'/name(c)) for c in schedule}))
        print('Finished: '+str(out/'report.md'), flush=True)


if __name__ == '__main__':
    main()
