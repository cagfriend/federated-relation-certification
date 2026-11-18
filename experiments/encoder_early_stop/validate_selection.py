"""Validate unlabeled snapshot selection and a targeted initialization recovery."""
import argparse
import copy
from pathlib import Path
from statistics import mean
from time import perf_counter
import warnings

from .run import predict, summarize

import numpy as np
import torch
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from threadpoolctl import threadpool_limits
from torch import nn
from torch.nn import functional as F

from experiments.external_pilot.common import SSLModel, Wire, batches, model_digest
from experiments.external_pilot.design import config
from experiments.external_pilot.evaluate import scores
from experiments.external_pilot.prepare import load, prepare, sha, write
from experiments.external_pilot.run import ROOT
from experiments.private_corrected_guard.engine import CorrectedGuardOurs
from experiments.private_corrected_guard.run import digest, seal_result
from experiments.public_scaling.certification import hard_relations, make_matching


NEW_SEEDS = (1205, 1206, 1207, 1208, 1209)
ROUNDS = 200
TAIL = 40
ACC_GUARD = .01
SHARED = ROOT / 'experiments/encoder_early_stop'


def snapshots(cfg, client, images, cached, requested):
    """Copy the requested states and verify the replay reaches the original cache."""
    torch.manual_seed(cfg['seed'] + 220 + client)
    width = cfg['widths'][client]
    model = SSLModel(width)
    decoder = nn.Linear(width, images.shape[1])
    opt = torch.optim.Adam(list(model.encoder.parameters()) + list(decoder.parameters()), lr=cfg['ae_lr'])
    result = {}
    step = 0
    for epoch in range(cfg['ae_epochs']):
        for ix in batches(len(images), cfg['local_batch'], cfg['seed'] + 101 * client + epoch):
            x = images[ix]
            opt.zero_grad()
            reconstruction = torch.sigmoid(decoder(F.relu(model.encoder.linear(x))))
            F.mse_loss(reconstruction, x).backward()
            opt.step()
            step += 1
            if step in requested:
                result[step] = copy.deepcopy(model)
    if set(result) != set(requested) or model_digest([model]) != model_digest([cached]):
        raise ValueError(f'Unexpected snapshot schedule or warm-up replay for client {client}')
    return result


@torch.no_grad()
def screen(cfg, client, model, train, edges):
    """Use local pseudo-label support and the unlabeled public occupancy only."""
    k = cfg['classes']
    x = model.encode(train['private'][client]).double().numpy()
    z = model.encode(train['public']).double().numpy()
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=ConvergenceWarning, message='Number of distinct clusters')
        km = KMeans(n_clusters=k, n_init=3, max_iter=100, random_state=cfg['seed'] + 101 * client).fit(x)
    centers = km.cluster_centers_
    labels = (z @ (2 * centers).T - np.sum(centers ** 2, axis=1)).argmax(axis=1)
    support = np.bincount(km.labels_, minlength=k)
    counts = np.bincount(labels, minlength=k)
    pair_count = int(counts @ (counts - 1))
    return dict(eligible=bool(np.all(support > 0)), private_support=support.tolist(),
                distinct_private_features=len(np.unique(x, axis=0)), private_zero=int(np.count_nonzero(~x.any(axis=1))),
                private_largest=float(support.max() / len(x)),
                public_largest=float(counts.max() / len(z)), public_counts=counts.tolist(),
                public_same_pair_numerator=pair_count, public_same_pair_rate=pair_count / (len(z) * (len(z) - 1)),
                graph_same_edge_rate=float(hard_relations(labels, edges).mean()),
                pseudo_digest=digest(km.labels_), centers_digest=digest(centers))


def select(candidates):
    eligible = [step for step, stats in candidates.items() if stats['eligible']]
    return min(eligible, key=lambda step: (candidates[step]['public_same_pair_numerator'], -step), default=None)


def run_arm(cfg, target, models, train, test, screened):
    fingerprints = [model_digest([model]) for model in models]
    a = CorrectedGuardOurs(models, cfg, Wire(), train['private'], train['public'],
                          initialization='centers', strength=.5, until=ROUNDS, all_clients=True)
    for c, (y, centers) in enumerate(zip(a.pseudo, a.centers)):
        if digest(y) != screened[c]['pseudo_digest'] or digest(centers) != screened[c]['centers_digest']:
            raise ValueError(f'Client {c} initialized differently from its screening')
    with torch.no_grad():
        features = [m.encode(test['test']).double().numpy() for m in models]
    truth = test['truth'].numpy()

    def checkpoint(rnd):
        return dict(round=rnd, clients=[
            dict(client=c, **scores(truth, predict(z, h), cfg['classes']))
            for c, (z, h) in enumerate(zip(features, a.heads))
        ])

    checkpoints = [checkpoint(0)]
    rows, audited = [], 0
    for rnd in range(1, ROUNDS + 1):
        a.round(train['private'], train['public'], cfg['seed'], rnd)
        audited += a.audit()
        rates = [float(r.mean()) for r in a.last_relations]
        rows.append(dict(round=rnd, teacher_rates=rates, aggregate_rate=float(a.protocol.counts.mean() / len(models)),
                         target=summarize(a, target), head_digest=a.state_digest(),
                         target_digest=digest(a.protocol.counts)))
        if rnd % 10 == 0:
            checkpoints.append(checkpoint(rnd))
    if audited != ROUNDS * len(models) * len(a.edges) or fingerprints != [model_digest([m]) for m in models]:
        raise ValueError('Incomplete relation audit or a changed frozen model')
    return dict(rows=rows, checkpoints=checkpoints, encoder_hashes=fingerprints, graph_hash=digest(a.edges),
                relation_audits=audited, mismatches=0, bytes=a.traffic()['total_bytes'])


def measure(run, client):
    rounds = run['rows'][-TAIL:]
    checkpoints = run['checkpoints'][-(TAIL // 10):]
    last = checkpoints[-1]['clients']
    target = last[client]
    return dict(teacher_tail=mean(r['teacher_rates'][client] for r in rounds),
                aggregate_tail=mean(r['aggregate_rate'] for r in rounds),
                public_largest_tail=mean(r['target']['public_largest'] for r in rounds),
                test_largest_tail=mean(q['clients'][client]['largest'] for q in checkpoints),
                test_largest_final=target['largest'], acc=target['acc'], nmi=target['nmi'], ari=target['ari'],
                network_acc=mean(q['acc'] for q in last), network_nmi=mean(q['nmi'] for q in last),
                network_ari=mean(q['ari'] for q in last), worst_acc=min(q['acc'] for q in last),
                network_largest=max(q['largest'] for q in last),
                private_macro_recall=rounds[-1]['target']['private_macro_recall'],
                private_zero_recall=rounds[-1]['target']['private_zero_recall'],
                severe_events=sum(q['occupied'] == 1 or q['largest'] >= .99
                                  for cp in run['checkpoints'][1:] for q in cp['clients']),
                bytes=run['bytes'])


def assess(reference, candidate):
    metrics = ('teacher_tail', 'test_largest_tail')
    deltas = {m: candidate[m] - reference[m] for m in candidate}
    return dict(deltas=deltas, both_lower=all(deltas[m] < 0 for m in metrics),
                neither_higher=all(deltas[m] <= 0 for m in metrics),
                acc_guard=all(deltas[m] >= -ACC_GUARD - 1e-12 for m in ('acc', 'network_acc', 'worst_acc')))


def execute(out, cfg, partition, cache, client, steps, reference):
    models, train, meta = load(cache, partition, cfg)
    edges = make_matching(len(train['public']), cfg['seed'])
    stage_start = perf_counter()
    saved = snapshots(cfg, client, train['private'][client], models[client], steps)
    replay_seconds = perf_counter() - stage_start
    started = perf_counter()
    terminal = screen(cfg, client, models[client], train, edges)
    probes = {step: screen(cfg, client, model, train, edges) for step, model in saved.items()}
    # Recovery uses the historical terminal step 5 as the infeasible reference.
    if reference in probes and probes[reference] != terminal:
        raise ValueError('Terminal candidate differs from original cache screening')
    probes[reference] = terminal
    selected = select({step: probes[step] for step in steps})
    screening_seconds = perf_counter() - started
    shared = {c: screen(cfg, c, model, train, edges) for c, model in enumerate(models) if c != client}
    undeclared_blockers = [c for c, stats in shared.items() if not stats['eligible']]
    label = f"{cfg['seed']}_{partition}_c{client}"
    arms, results = {}, {}
    # Record the decision before opening the labeled evaluation file.
    decision = dict(seed=cfg['seed'], partition=partition, target=client, selected=selected, reference=reference,
                    screening=probes, shared_clients=shared, cache_files=meta['files'],
                    shared_blocked_clients=undeclared_blockers, replay_with_copy_seconds=replay_seconds,
                    candidate_screening_seconds=screening_seconds)
    write(out / 'decisions' / f'{label}.json', decision)
    test = torch.load(cache / partition / 'evaluation.pt', weights_only=True)
    for step in sorted(probes, reverse=True):
        if undeclared_blockers or not probes[step]['eligible']:
            arms[step] = dict(status='initialization_blocked',
                              clients=sorted(undeclared_blockers + ([] if probes[step]['eligible'] else [client])))
            continue
        chosen = models.copy()
        if step != reference:
            chosen[client] = saved[step]
        result = run_arm(cfg, client, chosen, train, test, {**shared, client: probes[step]})
        path = out / 'runs' / f'{label}_step{step}.json'
        write(path, result)
        seal_result(path)
        arms[step] = dict(status='completed', summary=measure(result, client), sha256=sha(path),
                          relation_audits=result['relation_audits'])
        results[step] = result
    for a, b in zip(list(results.values()), list(results.values())[1:]):
        diff = [c for c, (u, v) in enumerate(zip(a['encoder_hashes'], b['encoder_hashes'])) if u != v]
        if diff != [client] or a['graph_hash'] != b['graph_hash']:
            raise ValueError('Comparison altered unrelated encoders or graph')
    comparison = None
    if reference in results and selected in results:
        comparison = assess(arms[reference]['summary'], arms[selected]['summary'])
    if reference == 5 and 2 in results and 3 in results:
        comparison = assess(arms[3]['summary'], arms[2]['summary'])
    print(f"{label}: selected step {selected}, {[(s, a['status']) for s, a in arms.items()]}", flush=True)
    return dict(**decision, arms=arms, comparison=comparison, decision_sha256=sha(out/'decisions'/f'{label}.json'))


def report(out, validation, recovery):
    lines = ['# STL-10 encoder snapshot validation', '',
             'Tail summaries use rounds 161–200 and test checkpoints 170/180/190/200.',
             'The selector uses only private cluster occupancy and unlabeled public occupancy.',
             'ACC guard permits a drop of one percentage point for the target, network mean and worst client.', '',
             '| Seed | Partition | Selected | Final-step baseline | Teacher tail baseline → selected | Test largest tail baseline → selected |',
             '|---|---|---:|---|---:|---:|']
    for item in validation:
        a = item['arms'][4]
        b = item['arms'].get(item['selected'], {})
        cols = ['—', '—']
        if item['comparison'] is not None:
            cols = [f"{a['summary'][k]:.2%} → {b['summary'][k]:.2%}" for k in ('teacher_tail', 'test_largest_tail')]
        lines.append(f"| {item['seed']} | {item['partition']} | {item['selected']} | {a['status']} | {' | '.join(cols)} |")
    lines += ['', '| Recovery step (client 2) | Status | Teacher tail | Test largest tail | Target ACC |',
              '|---|---|---:|---:|---:|']
    for step, arm in recovery['arms'].items():
        cols = ['—'] * 3
        if arm['status'] == 'completed':
            cols = [f"{arm['summary'][k]:.2%}" for k in ('teacher_tail', 'test_largest_tail', 'acc')]
        lines.append(f"| {step} | {arm['status']} | {' | '.join(cols)} |")
    (out/'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=SHARED / 'results_selection_validation')
    args = parser.parse_args()
    out = args.output.resolve()
    data = ROOT / 'experiments/stl10_transfer/data/stl10_binary'
    historical = SHARED / 'results_confirmation'
    if any(out.is_relative_to(p) or p.is_relative_to(out) for p in (data, historical)):
        parser.error('Output overlaps data or previous results')
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        parser.error('Output must be a new or empty directory')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    write(out/'design.json', dict(seeds=list(NEW_SEEDS), rounds=ROUNDS, tail_rounds=TAIL, target=1,
                                 partitions=config('pilot')['partitions'], candidates=[3, 4], guard=.5,
                                 accuracy_drop_guard=ACC_GUARD, reference=4,
                                 selector='all private clusters nonempty; minimize public same-cluster pair count; later step on tie',
                                 recovery=dict(seed=1204, partition='dirichlet_0.1', target=2, steps=[2, 3], reference=5),
                                 script_sha256=sha(Path(__file__))))
    with threadpool_limits(1):
        validation = []
        for seed in NEW_SEEDS:
            cfg = dict(config('pilot'), seed=seed)
            cache = out / 'cache' / str(seed)
            prepare(cache, data, cfg)
            for partition in cfg['partitions']:
                validation.append(execute(out, cfg, partition, cache, 1, (3, 4), 4))
        recovery = execute(out, dict(config('pilot'), seed=1204), 'dirichlet_0.1',
                           historical/'cache/1204', 2, (2, 3), 5)
    report(out, validation, recovery)
    write(out/'completed.json', dict(validation=validation, recovery=recovery,
                                     design_sha256=sha(out/'design.json'), report_sha256=sha(out/'report.md')))
    print(out/'report.md', flush=True)


if __name__ == '__main__':
    main()
