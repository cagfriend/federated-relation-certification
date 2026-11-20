"""Execute the same live head training with one exact relation path."""

from collections import Counter
from time import perf_counter

import numpy as np
import torch

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.evaluate import scores
from experiments.external_pilot.prepare import load
from experiments.private_corrected_guard.run import digest
from experiments.snapshot_certification_timing.design import checkpoints, require, seal, sealed, sha
from experiments.snapshot_certification_timing.engine import Engine
from experiments.snapshot_certification_timing.worker import battery, peak_bytes, suspend_clock
from experiments.snapshot_external_comparison.selection import select_models
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import load_bank


def load_context(source, ref, base):
    case = ref['case']
    cache = source/'cache'/str(case['seed'])
    models, train, meta = load(cache, case['partition'], base)
    require(meta['files'] == ref['input_files'] and meta['initial_model_digest'] == ref['initial_model_digest'],
            'Preparation cache differs from the confirmation trajectory')
    return models, train, meta


def selection_core(selection):
    return [{**{k: v for k, v in row.items() if k not in ('candidates', 'elapsed_seconds')},
             'candidates': {str(k): v for k, v in row['candidates'].items()}} for row in selection]


def prepare_snapshot(source, ref, base, path, identity):
    models, train, meta = load_context(source, ref, base)
    start = perf_counter()
    models, selection = select_models(base, models, train)
    elapsed = perf_counter()-start
    require(selection_core(selection) == selection_core(ref['selection']) and
            model_digest(models) == ref['selected_model_digest'], 'Snapshot selection changed')
    path.parent.mkdir(exist_ok=True)
    weights = path.with_suffix('.pt')
    temporary = weights.with_suffix('.pt.part')
    torch.save([model.state_dict() for model in models], temporary)
    temporary.replace(weights)
    seal(path, dict(manifest=identity, model_sha=sha(weights), ae_seconds=meta['common_ae_seconds'],
                    selection_seconds=elapsed))


def run(source, ref, base, snapshot_path, bank, method, *, audit, prefix=None):
    case, cfg = ref['case'], ref['cfg']
    rounds = prefix or cfg['rounds']
    models, train, _ = load_context(source, ref, base)
    selection = sealed(snapshot_path)
    weights = snapshot_path.with_suffix('.pt')
    require(sha(weights) == selection['model_sha'], 'Selected weights changed')
    for model, state in zip(models, torch.load(weights, weights_only=True), strict=True):
        model.load_state_dict(state)
    require(model_digest(models) == ref['selected_model_digest'], 'Selected encoder differs from confirmation')
    public, ids = load_bank(source, case, train, bank)
    # Realize the mapped input before setup timing.
    public = public.clone()
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    _ = np.ones((32, 32)) @ np.ones((32, 32))
    _ = torch.ones((32, 32)) @ torch.ones((32, 32))
    input_peak = peak_bytes()
    power = Counter()

    def power_check():
        state = battery()
        power['unknown' if state is None else ('ac' if state else 'battery')] += 1

    if not audit:
        power_check()
    start_sleep = suspend_clock()
    started = perf_counter()
    algo = Engine(models, cfg, Wire(), train['private'], public, method=method, initialization='centers',
                  strength=.5, until=cfg['rounds'], all_clients=True)
    setup = perf_counter()-started
    require(algo.state_digest() == ref['initial_head_digest'] and digest(algo.edges) == ref['graph_digest']
            and digest(ids.numpy()) == ref['public_ids_digest'], 'Initial head, graph or public IDs changed')
    for pseudo, centers, entry in zip(algo.pseudo, algo.centers, ref['selection'], strict=True):
        expected = entry['candidates'][str(entry['selected'])]
        require(digest(pseudo) == expected['pseudo_digest'] and digest(centers) == expected['centers_digest'],
                'Initial targets or centers differ from confirmation')

    rows, observed, evaluations = [], [], []
    ticks = set(checkpoints(cfg))
    if audit:
        cache = source/'cache'/str(case['seed'])/case['partition']
        evaluation = torch.load(cache/'evaluation.pt', weights_only=True)
        with torch.no_grad():
            features = [model.encode(evaluation['test']).double().numpy() for model in models]
        truth = evaluation['truth'].numpy()
        path = source/'traces'/f'{cell_id(case)}.npz'
        with np.load(path, allow_pickle=False) as trace:
            exact = trace['relations']
            teacher_hashes = [(trace[f'w{i}'], trace[f'b{i}']) for i in range(len(algo.heads))]

    def evaluate(round_id):
        clients = [dict(client=i, **scores(truth, (x@head.w.T+head.b).argmax(1), cfg['classes']))
                   for i, (x, head) in enumerate(zip(features, algo.heads, strict=True))]
        evaluation = dict(round=round_id, clients=clients)
        require(evaluation == ref['quality'][len(evaluations)], f'Round {round_id}: quality differs')
        evaluations.append(evaluation)

    if audit:
        evaluate(0)
    expected_edges = min(len(algo.edges), cfg['public_steps']*cfg['relation_batch'])
    comparisons = 0
    for rnd in range(1, rounds+1):
        started = perf_counter()
        stat = algo.round(train['private'], public, cfg['seed'], rnd)
        elapsed = perf_counter()-started
        vecs, counts = algo.last_relations, algo.protocol.counts
        orders = stat['public_orders']
        require(all(len(order) == expected_edges for order in orders), 'Student batch size changed')
        current = algo.traffic()
        head = algo.state_digest()
        require(head == ref['head_digests'][rnd-1] and current == ref['traffic'][rnd-1],
                f'Round {rnd}: training head or communication differs from the confirmation trajectory')
        observed.append(dict(head=head, relations=[digest(x) for x in vecs], counts=digest(counts),
                             teacher=[(digest(w), digest(b)) for w, b in algo.last_snapshot],
                             orders=[digest(x) for x in orders],
                             targets=[digest(t[o]) for t, o in zip(stat['consumed'], orders, strict=True)],
                             private_losses=stat['private_losses'], public_losses=stat['public_losses']))
        if audit:
            require(np.array_equal(counts, np.sum(vecs, axis=0)), f'Round {rnd}: aggregation differs')
            for i, (rel, (w, b), target, order) in enumerate(
                    zip(vecs, algo.last_snapshot, stat['consumed'], orders, strict=True)):
                weights, biases = teacher_hashes[i]
                perm = np.random.default_rng(np.random.SeedSequence(
                    [cfg['seed'], 402, i, rnd, 0])).permutation(len(algo.edges))[:expected_edges]
                require(np.array_equal(rel, np.unpackbits(exact[rnd-1, i], count=len(algo.edges))) and
                        np.array_equal(w, weights[rnd-1]) and np.array_equal(b, biases[rnd-1]) and
                        np.array_equal(target, counts/len(vecs)) and np.array_equal(order, perm),
                        f'Round {rnd}, client {i}: relation, teacher or consumed order/target differs')
                comparisons += len(rel)
            if rnd in ticks:
                evaluate(rnd)
        else:
            rows.append(dict(round=rnd, seconds=elapsed, endpoints=sum(stat['endpoints']),
                             **{k: stat[k] for k in ('private_seconds','generation_seconds',
                                                     'exchange_seconds','public_seconds')}))
            if rnd in ticks or rnd == rounds:
                power_check()
    end_sleep = suspend_clock()
    require(model_digest(models) == ref['selected_model_digest'], 'Frozen encoder changed')
    return dict(observed=observed, timing=rows, evaluations=evaluations, comparisons=comparisons,
                setup_seconds=None if audit else setup, traffic=current, cache_bytes=algo.cache_bytes(),
                protocol_bytes=algo.protocol.persistent_bytes(), input_peak_bytes=input_peak,
                process_peak_bytes=peak_bytes(), power=dict(power),
                suspend_seconds=None if None in (start_sleep, end_sleep) else max(0., end_sleep-start_sleep))
