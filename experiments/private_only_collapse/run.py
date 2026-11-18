"""Private-only ablation, paired with verified historical public-on runs."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import numpy as np
import torch
from threadpoolctl import threadpool_limits

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.design import config
from experiments.external_pilot.evaluate import evaluate
from experiments.external_pilot.prepare import load, read, sha, write
from experiments.external_pilot.run import ROOT, sources
from experiments.head_initialization.probes import distribution
from experiments.private_corrected_guard.engine import CorrectedGuardOurs
from experiments.private_corrected_guard.run import digest, name, seal_result, verify_seal
from experiments.public_scaling.protocol import Traffic
from .report import build


def require(condition, message):
    if not condition:
        raise ValueError(message)


def rounds_to_score(cfg):
    return [0] + [r for r in range(1, cfg['rounds'] + 1) if r % cfg['eval_every'] == 0 or r == cfg['rounds']]


def anchor(history, cache, cfg, case, current_sources):
    manifest_path = history/'manifest.json'
    manifest = read(manifest_path)
    path = history/'runs'/name(case)
    verify_seal(path)
    checksum = sha(path)
    require(read(history/'completed.json')['hashes'][path.name] == checksum, 'Historical completion hash mismatch')
    old = read(path)
    require(old['case'] == case and old['config'] == manifest['config'] == cfg and
            old['input_manifest_sha256'] == sha(manifest_path), 'Historical run identity mismatch')
    recorded = {k.replace('\\', '/'): v for k, v in manifest['sources'].items()}
    current = {k.replace('\\', '/'): v for k, v in current_sources.items()}
    for p in ('private_corrected_guard/engine.py', 'early_cluster_guard/engine.py', 'external_pilot/ours.py',
              'private_prior/training.py', 'public_scaling/head.py', 'head_initialization/probes.py',
              'external_pilot/evaluate.py', 'external_pilot/prepare.py', 'public_scaling/certification.py'):
        k = 'experiments/' + p
        require(k in recorded and recorded[k] == current.get(k), 'Historical source mismatch: ' + k)
    part = case['partition']
    cache_manifest = cache/part/'manifest.json'
    meta = read(cache_manifest)
    cache_hashes = {k.replace('\\', '/'): v for k, v in manifest['reference_hashes'].items()}
    require(cache_hashes.get(f'cache/{part}/manifest.json') == sha(cache_manifest) and
            old['cache_files'] == meta['files'] and old['initial_model_digest'] == meta['initial_model_digest'],
            'Historical cache mismatch')
    n = cfg['rounds']
    require([r['round'] for r in old['rows']] == list(range(1, n+1)) and
            [r['round'] for r in old['evaluations']] == rounds_to_score(cfg) and
            [(r['round'], r['stage']) for r in old['diagnostics']] == [(0, 'initial')] +
            [(i, s) for i in range(1, n+1) for s in ('T0', 'T1', 'T2')], 'Historical trajectory incomplete')
    require(old['mismatches'] == 0 and old['relation_comparisons'] == 6*(cfg['public_size']//2)*n,
            'Historical relation audit incomplete')
    return old, checksum


def observe(a, rnd, stage):
    clients, rates = [], []
    for c, (h, x, z, y) in enumerate(zip(a.heads, a.private, a.public, a.pseudo)):
        private = distribution(x, h.w, h.b, a.cfg['classes'], y)
        labels = (x@h.w.T+h.b).argmax(1)
        private['pseudo_recall'] = [float(np.mean(labels[y == k] == k)) if np.any(y == k) else None
                                    for k in range(a.cfg['classes'])]
        clients.append(dict(client=c, private=private, public=distribution(z, h.w, h.b, a.cfg['classes'])))
        if stage == 'T1':
            pred = (z@h.w.T+h.b).argmax(1)
            rates.append(float(np.mean(pred[a.edges[:, 0]] == pred[a.edges[:, 1]])))
    return dict(round=rnd, stage=stage, clients=clients, head_digest=a.state_digest(),
                teacher_positive_rates=rates if stage == 'T1' else None)


def check_first(result, old):
    x, y = result['diagnostics'], old['diagnostics']
    require(all(x[i]['clients'] == y[i]['clients'] and len(x[i]['clients']) == 6 for i in range(3)) and
            x[2]['teacher_positive_rates'] == y[2]['teacher_positive_rates'], 'Initial, T0 or first T1 probes changed')
    require(result['evaluations'][0] == old['evaluations'][0] and
            result['private_correction'] == old['private_correction'], 'Initial scores or priors changed')
    keys = ('centers_digest', 'pseudo_digest', 'pseudo_histogram')
    require(result['centers_and_labels'] == [{k: item[k] for k in keys} for item in old['initial_checks']],
            'Center or pseudo-label identity changed')
    before, after = old['rows'][0]['stats'], result['rows'][0]['stats']
    require(before['private_loss'] == after['private_loss'], 'First private loss changed')
    def strip_time(rows):
        return [{k: v for k, v in r.items() if k != 'seconds'} for r in rows]
    require(strip_time(before['guard_clients']) == strip_time(after['guard_clients']), 'First private guard changed')


def private_step(a, seed, rnd):
    """Keep the existing per-client training kernel, without calling the public round path."""
    a.guard_stats = []
    losses = [a.private_update(h, a.private[c], a.pseudo[c], a.config, seed, c, rnd)[0]
              for c, h in enumerate(a.heads)]
    return dict(private_loss=float(np.mean(losses)), guard_clients=a.guard_stats, public_updates=0)


class DisabledProtocol:
    """Skip even graph registration; fail fast if a training exchange is attempted."""
    def __init__(self, *args, **kwargs):
        self.traffic = Traffic()

    def exchange(self, *args, **kwargs):
        raise RuntimeError('Private-only rounds cannot exchange relations')


def run_case(out, cache, cfg, case, old, checksum):
    part = case['partition']
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    models, train, meta = load(cache, part, cfg)
    eval_data = torch.load(cache/part/'evaluation.pt', weights_only=True)
    # The inherited constructor registers the graph before round 1. Substitute only
    # the protocol constructor in this isolated worker so initialization is otherwise identical.
    with patch('experiments.external_pilot.ours.RelationProtocol', new=DisabledProtocol):
        a = CorrectedGuardOurs(models, cfg, Wire(), train['private'], train['public'], initialization='centers',
                               strength=case['strength'], until=cfg['rounds'], all_clients=True)
    with torch.no_grad():
        test_features = [m.encode(eval_data['test']).double().numpy() for m in models]

    def score(rnd):
        q = evaluate(a, train['private'], eval_data, cfg)
        for c, h in enumerate(a.heads):
            q['clients'][c]['native_confidence'] = distribution(test_features[c], h.w, h.b, cfg['classes'])
        return dict(round=rnd, **q)

    d = [observe(a, 0, 'initial')]
    result = dict(case=case, config=cfg, anchor_sha256=checksum, manifest_sha256=sha(out/'manifest.json'),
                  graph_digest=digest(a.edges), private_correction=dict(all_clients=True,
                                           log_priors=[p.tolist() for p in a.all_log_priors]),
                  centers_and_labels=[dict(centers_digest=digest(c), pseudo_digest=digest(y),
                                           pseudo_histogram=np.bincount(y, minlength=cfg['classes']).tolist())
                                      for c, y in zip(a.centers, a.pseudo)], rows=[], diagnostics=d, evaluations=[score(0)])
    for rnd in range(1, cfg['rounds']+1):
        d.append(observe(a, rnd, 'T0'))
        stats = private_step(a, cfg['seed'], rnd)
        d.append(observe(a, rnd, 'T1'))
        require(not a.generators and a.last_snapshot is None and all(v == 0 for v in a.traffic().values()),
                'Private-only path unexpectedly generated or transmitted training relations')
        result['rows'].append(dict(round=rnd, stats=stats, traffic=a.traffic(), head_digest=a.state_digest()))
        if rnd == 1:
            check_first(result, old)
        if rnd in rounds_to_score(cfg):
            result['evaluations'].append(score(rnd))
            print(f"{part} guard={case['strength']:g}: {rnd}/{cfg['rounds']}", flush=True)
    require(model_digest(models) == meta['initial_model_digest'] and digest(a.edges) == result['graph_digest'],
            'Frozen encoder or probe graph changed')
    path = out/'runs'/name(case)
    write(path, result)
    seal_result(path)


def verify_result(out, cfg, case, old, checksum):
    path = out/'runs'/name(case)
    verify_seal(path)
    r = read(path)
    require(r['manifest_sha256'] == sha(out/'manifest.json') and r['anchor_sha256'] == checksum and
            r['case'] == case and r['config'] == cfg, 'Run identity mismatch')
    check_first(r, old)
    n, d = cfg['rounds'], r['diagnostics']
    require([(s['round'], s['stage']) for s in d] == [(0, 'initial')] +
            [(i, stage) for i in range(1, n+1) for stage in ('T0', 'T1')] and
            [s['round'] for s in r['evaluations']] == rounds_to_score(cfg) and
            [s['round'] for s in r['rows']] == list(range(1, n+1)), 'Incomplete diagnostic run')
    for i, row in enumerate(r['rows']):
        require(d[2*i]['head_digest'] == d[2*i+1]['head_digest'] and d[2*i+2]['head_digest'] == row['head_digest'] and
                row['stats']['public_updates'] == 0 and row['traffic'] == {},
                'Public-off invariant failed')
    return r


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', choices=('pilot', 'smoke'), default='pilot')
    parser.add_argument('--history')
    parser.add_argument('--cache')
    parser.add_argument('--output')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--worker', type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    cfg = config(args.preset)
    pilot = args.preset == 'pilot'
    history = Path(args.history or ROOT/('experiments/private_corrected_guard/results_pilot' if pilot else
                                        'outputs/private_corrected_guard_verified_smoke')).resolve()
    cache = Path(args.cache or ROOT/('experiments/external_pilot/results_pilot_observed/cache' if pilot else
                                    'outputs/private_corrected_guard_checks/reference/cache')).resolve()
    out = Path(args.output or ROOT/f'experiments/private_only_collapse/results_{args.preset}').resolve()
    require(not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (history, cache)), 'Output overlaps input')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    schedule = [dict(partition=p, initialization='centers', all_clients=True, until=cfg['rounds'],
                     setting=f'corrected_guard_{s:g}', strength=s) for p in cfg['partitions'] for s in (0., .5)]
    source_hashes = sources()
    anchored = [anchor(history, cache, cfg, c, source_hashes) for c in schedule]
    manifest = dict(config=cfg, schedule=schedule, history=str(history), cache=str(cache),
                    history_manifest_sha256=sha(history/'manifest.json'), history_complete_sha256=sha(history/'completed.json'),
                    source_hashes=source_hashes, anchor_hashes={name(c): a[1] for c, a in zip(schedule, anchored)},
                    design_sha256=sha(Path(__file__).with_name('README.md')))
    with threadpool_limits(1):
        if args.worker is not None:
            require(read(out/'manifest.json') == manifest, 'Worker inputs changed')
            run_case(out, cache, cfg, schedule[args.worker], *anchored[args.worker])
            return
        if (out/'manifest.json').exists():
            require(args.resume and read(out/'manifest.json') == manifest, 'Use --resume with identical inputs or a new output')
        else:
            require(not out.exists() or not any(out.iterdir()), 'Output is not empty')
            write(out/'manifest.json', manifest)
        done = read(out/'completed.json') if (out/'completed.json').exists() else None
        paired = []
        for i, (c, (old, checksum)) in enumerate(zip(schedule, anchored)):
            path = out/'runs'/name(c)
            if done:
                require(path.is_file() and sha(path) == done['hashes'].get(path.name), 'Completed result changed')
            if not path.exists():
                print(f'Starting {i+1}/{len(schedule)}: {path.name}', flush=True)
                env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', LOKY_MAX_CPU_COUNT='1')
                subprocess.run([sys.executable, '-m', 'experiments.private_only_collapse.run', '--preset', args.preset,
                                '--history', str(history), '--cache', str(cache), '--output', str(out), '--worker', str(i)],
                               cwd=ROOT, env=env, check=True)
            else:
                print(f'Retaining {path.name}', flush=True)
            paired.append((c, old, verify_result(out, cfg, c, old, checksum)))
        build(out, paired, cfg)
        write(out/'completed.json', dict(runs=len(paired), hashes={name(c): sha(out/'runs'/name(c)) for c in schedule}))
        print('Finished: ' + str(out/'report.md'), flush=True)


if __name__ == '__main__':
    main()
