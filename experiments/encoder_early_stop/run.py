"""Compare client1's third and fourth AE snapshots during 40 collaborative rounds."""
import argparse
import copy
import csv
import os
from pathlib import Path
from statistics import mean

os.environ.setdefault('LOKY_MAX_CPU_COUNT', '1')

import numpy as np
import torch
from threadpoolctl import threadpool_limits
from torch import nn
from torch.nn import functional as F

from experiments.external_pilot.common import SSLModel, Wire, batches, model_digest
from experiments.external_pilot.design import config
from experiments.external_pilot.evaluate import scores
from experiments.external_pilot.prepare import load, read, sha, write
from experiments.external_pilot.run import ROOT, sources
from experiments.private_corrected_guard.engine import CorrectedGuardOurs
from experiments.private_corrected_guard.run import digest, seal_result
from experiments.private_only_collapse.run import anchor, require
from experiments.public_scaling.certification import hard_relations


CLIENT = 1
ROUNDS = 40
STEPS = (3, 4)


def earlier_encoder(cfg, private, cached):
    """Replay the original update schedule and retain step 3 only after validating step 4."""
    torch.manual_seed(cfg['seed'] + 220 + CLIENT)
    model = SSLModel(cfg['widths'][CLIENT])
    decoder = nn.Linear(cfg['widths'][CLIENT], private.shape[1])
    optimizer = torch.optim.Adam(list(model.encoder.parameters()) + list(decoder.parameters()),
                                 lr=cfg['ae_lr'])
    snapshot = None
    step = 0
    for epoch in range(cfg['ae_epochs']):
        for indices in batches(len(private), cfg['local_batch'], cfg['seed'] + 101 * CLIENT + epoch):
            optimizer.zero_grad()
            x = private[indices]
            reconstruction = torch.sigmoid(decoder(F.relu(model.encoder.linear(x))))
            F.mse_loss(reconstruction, x).backward()
            optimizer.step()
            step += 1
            if step == STEPS[0]:
                snapshot = copy.deepcopy(model)
    require(step == STEPS[1] and snapshot is not None, 'Unexpected AE update schedule')
    require(model_digest([model]) == model_digest([cached]), 'AE replay differs from historical cache')
    require(model_digest([snapshot]) != model_digest([cached]), 'AE snapshots are identical')
    return snapshot


def predict(x, head):
    return (x @ head.w.T + head.b).argmax(axis=1)


def summarize(algorithm, client):
    k = algorithm.cfg['classes']
    head = algorithm.heads[client]
    y = algorithm.pseudo[client]
    private = predict(algorithm.private[client], head)
    public = predict(algorithm.public[client], head)
    counts = np.bincount(public, minlength=k)
    recall = [float((private[y == i] == i).mean()) if np.any(y == i) else None for i in range(k)]
    return dict(client=client, private_fit=float((private == y).mean()),
                private_macro_recall=mean(v for v in recall if v is not None),
                private_zero_recall=sum(v == 0 for v in recall), private_recall=recall,
                private_counts=np.bincount(private, minlength=k).tolist(),
                public_counts=counts.tolist(), public_occupied=int(np.count_nonzero(counts)),
                public_largest=float(counts.max() / len(public)),
                projected_positive_rate=float(hard_relations(public, algorithm.edges).mean()))


def run_arm(cfg, models, train, test, step, historical):
    observations = []

    def probe(algorithm, rnd, stage):
        if stage == 'T0':
            return
        clients = [summarize(algorithm, c) for c in range(len(algorithm.heads))]
        row = dict(round=rnd, stage=stage, clients=clients)
        if stage == 'T2':
            actual = [float(r.mean()) for r in algorithm.last_relations]
            require(actual == [c['projected_positive_rate'] for c in observations[-1]['clients']],
                    'Teacher probe differs from generated relations')
            counts = algorithm.protocol.counts
            row.update(teacher_positive_rates=actual, target_mean=float(counts.mean() / len(clients)),
                       target_histogram=np.bincount(counts, minlength=len(clients) + 1).tolist(),
                       target_digest=digest(counts))
        observations.append(row)

    encoder_hashes = [model_digest([m]) for m in models]
    algorithm = CorrectedGuardOurs(models, cfg, Wire(), train['private'], train['public'],
                                  initialization='centers', diagnostic_callback=probe, strength=.5,
                                  until=cfg['rounds'], all_clients=True)
    with torch.no_grad():
        test_features = [m.encode(test['test']).double().numpy() for m in models]
    truth = test['truth'].numpy()

    def evaluate(rnd):
        clients = []
        for c, (z, head) in enumerate(zip(test_features, algorithm.heads)):
            pred = predict(z, head)
            # Native-head scores only. Test labels are fetched for this observer.
            clients.append(dict(client=c, **scores(truth, pred, cfg['classes'])))
        if step == STEPS[1]:
            reference = next(r for r in historical['evaluations'] if r['round'] == rnd)
            require([{'client': c['client'], **c['native_head']} for c in reference['clients']] == clients,
                    f'Step 4 scores differ from E36 at round {rnd}')
        return dict(round=rnd, clients=clients)

    init = [dict(pseudo_support=np.bincount(y, minlength=cfg['classes']).tolist(),
                 pseudo_digest=digest(y), centers_digest=digest(centers))
            for y, centers in zip(algorithm.pseudo, algorithm.centers)]
    for c, entry in enumerate(init):
        if step == STEPS[1] or c != CLIENT:
            old = historical['initial_checks'][c]
            require(entry == dict(pseudo_support=old['pseudo_histogram'], pseudo_digest=old['pseudo_digest'],
                                  centers_digest=old['centers_digest']), f'Unchanged client {c} initialization differs')

    probe(algorithm, 0, 'initial')
    checkpoints = [evaluate(0)]
    rows, comparisons = [], 0
    for rnd in range(1, ROUNDS + 1):
        algorithm.round(train['private'], train['public'], cfg['seed'], rnd)
        comparisons += algorithm.audit()
        head_digest = algorithm.state_digest()
        traffic = algorithm.traffic()
        if step == STEPS[1]:
            old = historical['rows'][rnd - 1]
            old_target = historical['diagnostics'][3 * rnd]['committed_target']
            require(old['round'] == rnd and old['head_digest'] == head_digest and old['traffic'] == traffic
                    and old_target['digest'] == observations[-1]['target_digest'],
                    f'Step 4 training differs from E36 at round {rnd}')
        rows.append(dict(round=rnd, head_digest=head_digest, traffic=traffic))
        if rnd % 10 == 0:
            checkpoints.append(evaluate(rnd))
    require(comparisons == ROUNDS * len(models) * len(algorithm.edges), 'Incomplete relation audit')
    require([model_digest([m]) for m in models] == encoder_hashes, 'A frozen encoder changed during training')
    return dict(ae_steps=step, encoder_hashes=encoder_hashes, initial=init, observations=observations,
                test_checkpoints=checkpoints, rows=rows, relation_comparisons=comparisons,
                relation_mismatches=0, e36_prefix_rounds=ROUNDS if step == STEPS[1] else 0)


def summarize_pair(partition, pair):
    rows = []
    for i, (control, early) in enumerate(zip(pair[4]['test_checkpoints'], pair[3]['test_checkpoints'])):
        for c, (a, b) in enumerate(zip(control['clients'], early['clients'])):
            rnd = control['round']
            obs = 2 * rnd
            z4 = pair[4]['observations'][obs]['clients'][c]
            z3 = pair[3]['observations'][obs]['clients'][c]
            row = dict(partition=partition, round=rnd, client=c)
            for key in ('largest', 'acc', 'nmi', 'ari', 'occupied', 'empty'):
                row[f'test_{key}_s4'], row[f'test_{key}_s3'] = a[key], b[key]
            for key in ('public_largest', 'private_macro_recall', 'private_zero_recall'):
                row[f'{key}_s4'], row[f'{key}_s3'] = z4[key], z3[key]
            key = 'teacher_positive_rates'
            if i == 0:
                row['same_cluster_edges_s4'], row['same_cluster_edges_s3'] = (
                    z4['projected_positive_rate'], z3['projected_positive_rate'])
            else:
                row['same_cluster_edges_s4'], row['same_cluster_edges_s3'] = (
                    pair[4]['observations'][obs][key][c], pair[3]['observations'][obs][key][c])
            rows.append(row)
    return rows


def report(out, rows):
    with (out / 'pairs.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = ['# Client 1 encoder early-stop diagnostic', '',
             'Arrows show step 4 control → step 3. Public clusters are measured after the round. '
             'Same-cluster edges are the actual teacher messages before public updates, or initial projections at round 0.',
             'Macro recall and zero-recall counts use each arm’s own fixed pseudo-labels.', '',
             '| Partition | Round | Public largest | Same-cluster edges | Test largest | Test ACC | Test NMI | Test ARI | Private macro recall | Zero recall |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in rows:
        if r['client'] != CLIENT:
            continue
        cols = [r['partition'], str(r['round'])]
        for k in ('public_largest', 'same_cluster_edges', 'test_largest', 'test_acc',
                  'test_nmi', 'test_ari', 'private_macro_recall', 'private_zero_recall'):
            fmt = 'd' if k == 'private_zero_recall' else '.2%'
            cols.append(f"{r[k + '_s4']:{fmt}} → {r[k + '_s3']:{fmt}}")
        lines.append('| ' + ' | '.join(cols) + ' |')
    (out / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'experiments/encoder_early_stop/results_pilot')
    args = parser.parse_args()
    out = args.output.resolve()
    cache = ROOT / 'experiments/external_pilot/results_pilot_observed/cache'
    history = ROOT / 'experiments/private_corrected_guard/results_pilot'
    if any(out.is_relative_to(p) or p.is_relative_to(out) for p in (cache, history)):
        parser.error('Output overlaps a historical input.')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('Output must be a new or empty directory.')

    cfg = config('pilot')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    source_hashes = sources()
    combined, results, provenance = [], {}, {}
    with threadpool_limits(1):
        for partition in cfg['partitions']:
            case = dict(partition=partition, initialization='centers', all_clients=True,
                        until=cfg['rounds'], setting='corrected_guard_0.5', strength=.5)
            old, checksum = anchor(history, cache, cfg, case, source_hashes)
            models, train, meta = load(cache, partition, cfg)
            test = torch.load(cache / partition / 'evaluation.pt', weights_only=True)
            earlier = earlier_encoder(cfg, train['private'][CLIENT], models[CLIENT])
            pair = {4: run_arm(cfg, models, train, test, 4, old)}
            print(f'{partition} step 4: exact E36 prefix match (40 rounds)', flush=True)
            modified = models.copy()
            modified[CLIENT] = earlier
            pair[3] = run_arm(cfg, modified, train, test, 3, old)
            differences = [c for c, (a, b) in enumerate(zip(pair[4]['encoder_hashes'], pair[3]['encoder_hashes'])) if a != b]
            require(differences == [CLIENT], 'Unexpected encoder differences between arms')
            print(f'{partition} step 3: 40 rounds completed', flush=True)
            results.update({f'{partition}_step{step}': result for step, result in pair.items()})
            combined.extend(summarize_pair(partition, pair))
            provenance[partition] = dict(cache_files=meta['files'], historical_run_sha256=checksum)

    out.mkdir(parents=True, exist_ok=True)
    for name, result in results.items():
        path = out / f'{name}.json'
        write(path, result)
        seal_result(path)
    report(out, combined)
    write(out / 'completed.json', dict(rounds=ROUNDS, target_client=CLIENT, config=cfg,
                                       provenance=provenance, probe_sha256=sha(Path(__file__)),
                                       reports={name: sha(out / name) for name in ('report.md', 'pairs.csv')},
                                       runs={name: sha(out / f'{name}.json') for name in results}))
    print(out / 'report.md', flush=True)


if __name__ == '__main__':
    main()
