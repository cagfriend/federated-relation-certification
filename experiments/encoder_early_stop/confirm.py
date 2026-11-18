"""Confirm the fixed three-versus-four update ablation on new STL-10 seeds."""
import argparse
from collections import Counter
from pathlib import Path
from statistics import mean

from .run import CLIENT, earlier_encoder, predict, summarize

import numpy as np
import torch
from threadpoolctl import threadpool_limits

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.design import config
from experiments.external_pilot.evaluate import scores
from experiments.external_pilot.prepare import load, prepare, sha, write
from experiments.external_pilot.run import ROOT
from experiments.private_corrected_guard.engine import CorrectedGuardOurs
from experiments.private_corrected_guard.run import digest, seal_result


SEEDS = (1202, 1203, 1204)
ROUNDS = 200
TAIL_START = 161


def run_arm(cfg, train, test, models):
    model_hashes = [model_digest([model]) for model in models]
    a = CorrectedGuardOurs(models, cfg, Wire(), train['private'], train['public'],
                          initialization='centers', strength=.5, until=ROUNDS, all_clients=True)
    initial = [dict(centers=digest(c), pseudo=digest(y),
                    support=np.bincount(y, minlength=cfg['classes']).tolist())
               for c, y in zip(a.centers, a.pseudo)]
    with torch.no_grad():
        z_test = [m.encode(test['test']).double().numpy() for m in models]
    truth = test['truth'].numpy()

    def checkpoint(rnd):
        return dict(round=rnd, clients=[
            dict(client=c, **scores(truth, predict(z, h), cfg['classes']))
            for c, (z, h) in enumerate(zip(z_test, a.heads))
        ])

    checks = [checkpoint(0)]
    before = [summarize(a, c) for c in range(len(models))]
    audit, rows = 0, []
    for rnd in range(1, ROUNDS + 1):
        a.round(train['private'], train['public'], cfg['seed'], rnd)
        audit += a.audit()
        teacher = [float(r.mean()) for r in a.last_relations]
        rows.append(dict(round=rnd, teacher=teacher, aggregate_rate=mean(teacher),
                         target=summarize(a, CLIENT), head_digest=a.state_digest(),
                         aggregate_digest=digest(a.protocol.counts)))
        if rnd % 10 == 0:
            checks.append(checkpoint(rnd))
    if audit != ROUNDS * len(models) * len(a.edges) or model_hashes != [model_digest([m]) for m in models]:
        raise ValueError('Incomplete oracle coverage or a modified frozen model')
    return dict(initial_encoders=model_hashes, initial_clusters=initial, initial_probe=before,
                checkpoints=checks, rows=rows, relation_audits=audit, mismatches=0,
                traffic=a.traffic(), graph_digest=digest(a.edges))


def compare(seed, partition, results):
    values = {}
    for step, r in results.items():
        tail = r['rows'][TAIL_START - 1:]
        last = r['checkpoints'][-1]['clients']
        target = last[CLIENT]
        check_tail = [q['clients'][CLIENT] for q in r['checkpoints'] if q['round'] >= TAIL_START]
        values[step] = dict(teacher_tail=mean(row['teacher'][CLIENT] for row in tail),
                            aggregate_tail=mean(row['aggregate_rate'] for row in tail),
                            public_largest_tail=mean(row['target']['public_largest'] for row in tail),
                            test_largest_tail=mean(q['largest'] for q in check_tail),
                            test_largest=target['largest'], test_acc=target['acc'],
                            test_nmi=target['nmi'], test_ari=target['ari'],
                            private_macro_recall=r['rows'][-1]['target']['private_macro_recall'],
                            private_zero_recall=r['rows'][-1]['target']['private_zero_recall'],
                            network_acc=mean(q['acc'] for q in last),
                            network_nmi=mean(q['nmi'] for q in last),
                            network_ari=mean(q['ari'] for q in last),
                            severe_events=sum(q['occupied'] == 1 or q['largest'] >= .99
                                              for cp in r['checkpoints'][1:] for q in cp['clients']),
                            bytes=r['traffic']['total_bytes'])
    early, control = values[3], values[4]
    return dict(seed=seed, partition=partition, step3=early, step4=control,
                both_lower=early['teacher_tail'] < control['teacher_tail']
                and early['test_largest_tail'] < control['test_largest_tail'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'experiments/encoder_early_stop/results_confirmation')
    args = parser.parse_args()
    data = ROOT / 'experiments/stl10_transfer/data/stl10_binary'
    out = args.output.resolve()
    if out.is_relative_to(data) or (out.exists() and (not out.is_dir() or any(out.iterdir()))):
        parser.error('Use a new or empty results directory outside the data directory.')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    source_files = ('train_X.bin', 'train_y.bin', 'unlabeled_X.bin', 'test_X.bin', 'test_y.bin')
    source_sizes = {name: (data / name).stat().st_size for name in source_files}
    out.mkdir(parents=True, exist_ok=True)
    write(out / 'design.json', dict(seeds=list(SEEDS), rounds=ROUNDS, steps=[4, 3], target_client=CLIENT,
                                   guard=.5, data_bytes=source_sizes, tail_start=TAIL_START,
                                   comparison='step3 lower on both tail teacher rate and tail test largest',
                                   code_sha256=sha(Path(__file__))))
    pairs, failures, audit_count = [], [], 0
    with threadpool_limits(1):
        for seed in SEEDS:
            cfg = dict(config('pilot'), seed=seed)
            cache = out / 'cache' / str(seed)
            prepare(cache, data, cfg)
            for partition in cfg['partitions']:
                models, train, meta = load(cache, partition, cfg)
                test = torch.load(cache / partition / 'evaluation.pt', weights_only=True)
                earlier = earlier_encoder(cfg, train['private'][CLIENT], models[CLIENT])
                pair = {}
                for step in (4, 3):
                    chosen = models.copy()
                    if step == 3:
                        chosen[CLIENT] = earlier
                    try:
                        result = run_arm(cfg, train, test, chosen)
                    except ValueError as exc:
                        if str(exc) != 'Registered correction requires every pseudo cluster nonempty':
                            raise
                        failures.append(dict(seed=seed, partition=partition, step=step, reason=str(exc)))
                        print(f'{seed} {partition} step {step}: unavailable under registered correction', flush=True)
                        continue
                    audit_count += result['relation_audits']
                    pair[step] = result
                    path = out / 'runs' / f'{seed}_{partition}_step{step}.json'
                    write(path, dict(seed=seed, partition=partition, step=step, cache_files=meta['files'], **result))
                    seal_result(path)
                    print(f'{seed} {partition} step {step}: completed {ROUNDS} rounds', flush=True)
                if len(pair) != 2:
                    continue
                control, early = pair[4], pair[3]
                changed = [c for c, (a, b) in enumerate(zip(control['initial_encoders'], early['initial_encoders'])) if a != b]
                if (changed != [CLIENT] or control['graph_digest'] != early['graph_digest']
                        or any(a != b for c, (a, b) in enumerate(zip(control['initial_clusters'], early['initial_clusters']))
                               if c != CLIENT)):
                    raise ValueError('Pair changed inputs beyond the target encoder and its derived clusters')
                pairs.append(compare(seed, partition, pair))
    wins = Counter(p['partition'] for p in pairs if p['both_lower'])
    write(out / 'completed.json', dict(pairs=pairs, failures=failures, paired_wins=dict(wins),
                                      relation_audits=audit_count,
                                      run_checksums={p.name: sha(p) for p in sorted((out / 'runs').glob('*_step?.json'))}))
    lines = ['Seed | Partition | Tail teacher rate (4 → 3) | Tail test largest (4 → 3)',
             '---|---|---:|---:']
    for p in pairs:
        a, b = p['step4'], p['step3']
        lines.append(f"{p['seed']} | {p['partition']} | {a['teacher_tail']:.2%} → {b['teacher_tail']:.2%} |"
                     f" {a['test_largest_tail']:.2%} → {b['test_largest_tail']:.2%}")
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(out / 'report.md', flush=True)


if __name__ == '__main__':
    main()
