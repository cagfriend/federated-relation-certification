"""Train Demand against the immutable E42/E43 reference inputs and outputs."""

from collections import Counter
from time import perf_counter

import numpy as np
import torch

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.evaluate import scores
from experiments.private_corrected_guard.run import digest
from experiments.snapshot_certification_timing.design import checkpoints, require, sealed, sha
from experiments.snapshot_certification_timing.worker import battery, peak_bytes, suspend_clock
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import load_bank

from ..full_training.worker import load_context
from .engine import DemandEngine

STUDENT_FIELDS = ('head', 'teacher', 'orders', 'targets', 'private_losses', 'public_losses')


def student_trace(record):
    return {k: record[k] for k in STUDENT_FIELDS}


def run(confirmation, ref, base, prep, bank, baseline, *, audit, prefix=None):
    case, cfg = ref['case'], ref['cfg']
    rounds = prefix or cfg['rounds']
    models, train, _ = load_context(confirmation, ref, base)
    weights = prep.with_suffix('.pt')
    require(sha(weights) == sealed(prep)['model_sha'], 'Selected weights changed')
    for model, state in zip(models, torch.load(weights, weights_only=True), strict=True):
        model.load_state_dict(state)
    require(model_digest(models) == ref['selected_model_digest'], 'Wrong frozen encoder')
    public, ids = load_bank(confirmation, case, train, bank)
    public = public.clone()
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    _ = np.ones((32, 32)) @ np.ones((32, 32))
    _ = torch.ones((32, 32)) @ torch.ones((32, 32))
    input_peak = peak_bytes()
    power = Counter()

    def power_check():
        ac = battery()
        power['unknown' if ac is None else ('ac' if ac else 'battery')] += 1

    if not audit:
        power_check()
    sleep_start = suspend_clock()
    start = perf_counter()
    engine = DemandEngine(models, cfg, Wire(), train['private'], public, initialization='centers',
                          strength=.5, until=cfg['rounds'], all_clients=True)
    setup = perf_counter()-start
    require(engine.state_digest() == ref['initial_head_digest'] and digest(engine.edges) == ref['graph_digest']
            and digest(ids.numpy()) == ref['public_ids_digest'], 'Initial head, graph or public IDs changed')
    for pseudo, centers, entry in zip(engine.pseudo, engine.centers, ref['selection'], strict=True):
        expected = entry['candidates'][str(entry['selected'])]
        require(digest(pseudo) == expected['pseudo_digest'] and digest(centers) == expected['centers_digest'],
                'Initial pseudo-labels or centers changed')

    evaluations, observed, rows, scope = [], [], [], []
    audited_edges = 0
    ticks = set(checkpoints(cfg))
    if audit:
        with np.load(confirmation/'traces'/f'{cell_id(case)}.npz', allow_pickle=False) as trace:
            exact = trace['relations']
        file = confirmation/'cache'/str(case['seed'])/case['partition']/'evaluation.pt'
        evaluation = torch.load(file, weights_only=True)
        truth = evaluation['truth'].numpy()
        with torch.no_grad():
            features = [model.encode(evaluation['test']).double().numpy() for model in models]

    def evaluate(rnd):
        clients = [dict(client=i, **scores(truth, (x@head.w.T+head.b).argmax(1), cfg['classes']))
                   for i, (x, head) in enumerate(zip(features, engine.heads, strict=True))]
        outcome = dict(round=rnd, clients=clients)
        require(outcome == ref['quality'][len(evaluations)], f'Round {rnd}: native quality changed')
        evaluations.append(outcome)

    setup_traffic = engine.traffic()
    if audit:
        evaluate(0)
    for rnd in range(1, rounds+1):
        start = perf_counter()
        stats = engine.round(train['private'], public, cfg['seed'], rnd)
        elapsed = perf_counter()-start
        union, votes, counts = engine.last_union, engine.last_relations, engine.last_counts
        spot = dict(head=engine.state_digest(),
                    teacher=[[digest(w), digest(b)] for w, b in engine.last_snapshot],
                    orders=[digest(o) for o in stats['public_orders']],
                    targets=[digest(t) for t in stats['consumed']],
                    private_losses=stats['private_losses'], public_losses=stats['public_losses'])
        require(spot == student_trace(baseline['observed'][rnd-1]),
                f'Round {rnd}: Demand changed the actual student trajectory')
        observed.append(dict(spot, union=digest(union), votes=[digest(v) for v in votes], counts=digest(counts)))
        scope.append(dict(round=rnd, edges=len(union), endpoints=sum(stats['endpoints'])))
        if audit:
            require(np.array_equal(union, np.unique(np.concatenate(stats['public_orders']))),
                    f'Round {rnd}: wrong requested edge union')
            full = np.unpackbits(exact[rnd-1], count=len(engine.edges), axis=1)
            require(np.array_equal(np.asarray(votes), full[:, union]) and
                    np.array_equal(counts, full[:, union].sum(axis=0)), f'Round {rnd}: wrong Demand votes or counts')
            audited_edges += len(votes)*len(union)
            if rnd in ticks:
                evaluate(rnd)
        else:
            rows.append(dict(round=rnd, seconds=elapsed, endpoints=sum(stats['endpoints']),
                             **{k: stats[k] for k in ('private_seconds','coordination_seconds','generation_seconds',
                                                     'exchange_seconds','public_seconds')}))
            if rnd in ticks or rnd == rounds:
                power_check()
    sleep_end = suspend_clock()
    require(model_digest(models) == ref['selected_model_digest'], 'Frozen encoder changed')
    traffic = engine.traffic()
    breakdown = dict(engine.protocol.breakdown)
    require(traffic['total_bytes'] == setup_traffic['total_bytes'] + sum(breakdown.values()),
            'Communication accounting does not match serialized packet bytes')
    return dict(observed=observed, evaluations=evaluations, timing=rows, scope=scope, comparisons=audited_edges,
                setup_seconds=None if audit else setup, cache_bytes=engine.cache_bytes(),
                protocol_bytes=engine.protocol.persistent_bytes(), traffic=traffic, traffic_breakdown=breakdown,
                setup_traffic=setup_traffic, input_peak_bytes=input_peak, process_peak_bytes=peak_bytes(),
                power=dict(power), suspend_seconds=None if None in (sleep_start, sleep_end)
                else max(0., sleep_end-sleep_start))
