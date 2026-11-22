"""Train one method from the same selected STL-10 snapshot."""

from collections import Counter
from time import perf_counter
from unittest.mock import patch

import numpy as np
import torch

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.evaluate import scores
from experiments.private_corrected_guard.run import digest
from experiments.snapshot_certification_timing import engine
from experiments.snapshot_certification_timing.design import checkpoints, require, sealed, sha
from experiments.snapshot_certification_timing.worker import battery, suspend_clock
from experiments.snapshot_graph_scaling.inputs import load_bank

from ..full_training.worker import load_context
from ..numerical_boundary.guard import GuardedGenerator

STAGES = ('private_seconds', 'generation_seconds', 'exchange_seconds', 'public_seconds')


class TrainingGuard(GuardedGenerator):
    def generate(self, weights, bias):
        relations, stats = super().generate(weights, bias)
        # The archived guard only reports endpoints on dense fallback.
        # The live engine also expects the number of certified edges.
        if self.fallback:
            stats['certified_edges_before_refresh'] = 0
        return relations, stats


def guarded_factory(features, weights, bias, edges, mode):
    require(mode == 'relation', 'Combined guard requires relation mode')
    return TrainingGuard(features, weights, bias, edges, interval=True, dense=True)


def train(confirmation, ref, base, snapshot, bank, method, rounds):
    started = perf_counter()
    suspend_start = suspend_clock()
    power = Counter()

    def sample_power():
        value = battery()
        power['unknown' if value is None else 'ac' if value else 'battery'] += 1

    sample_power()
    case, cfg = ref['case'], ref['cfg']
    models, data, meta = load_context(confirmation, ref, base)
    preparation = sealed(snapshot)
    weights = snapshot.with_suffix('.pt')
    require(sha(weights) == preparation['model_sha'], 'Selected model file changed')
    for model, state in zip(models, torch.load(weights, weights_only=True), strict=True):
        model.load_state_dict(state)
    require(model_digest(models) == ref['selected_model_digest'], 'Selected model digest changed')
    public, ids = load_bank(confirmation, case, data, bank)
    public = public.clone()
    cache = confirmation/'cache'/str(case['seed'])/case['partition']
    evaluation = torch.load(cache/'evaluation.pt', weights_only=True)
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    _ = np.ones((32, 32)) @ np.ones((32, 32))
    _ = torch.ones((32, 32)) @ torch.ones((32, 32))
    load_seconds = perf_counter() - started

    setup_start = perf_counter()
    algo = engine.Engine(models, cfg, Wire(), data['private'], public, method='D',
                         initialization='centers', strength=.5, until=cfg['rounds'], all_clients=True)
    setup_seconds = perf_counter() - setup_start
    require(algo.state_digest() == ref['initial_head_digest'] and digest(algo.edges) == ref['graph_digest']
            and digest(ids.numpy()) == ref['public_ids_digest'], 'Initial head, graph or public IDs changed')
    for pseudo, centers, entry in zip(algo.pseudo, algo.centers, ref['selection'], strict=True):
        expected = entry['candidates'][str(entry['selected'])]
        require(digest(pseudo) == expected['pseudo_digest'] and digest(centers) == expected['centers_digest'],
                'Private targets or centers changed')

    evaluation_start = perf_counter()
    with torch.no_grad():
        features = [model.encode(evaluation['test']).double().numpy() for model in models]
    truth = evaluation['truth'].numpy()
    evaluation_seconds = perf_counter() - evaluation_start
    rows, quality = [], []

    def evaluate(rnd):
        start = perf_counter()
        clients = [dict(client=i, **scores(truth, (x@head.w.T+head.b).argmax(1), cfg['classes']))
                   for i, (x, head) in enumerate(zip(features, algo.heads, strict=True))]
        quality.append(dict(round=rnd, clients=clients))
        return perf_counter() - start

    evaluation_seconds += evaluate(0)
    require(quality[0] == ref['quality'][0], 'Initial test predictions differ from the frozen protocol')
    triggers = Counter()
    ticks = {i for i in checkpoints(cfg) if i <= rounds} | {rounds}
    budget = min(len(algo.edges), cfg['public_steps']*cfg['relation_batch'])
    factory = guarded_factory if method == 'C' else engine.make_generator
    with patch.object(engine, 'make_generator', factory):
        for rnd in range(1, rounds+1):
            before = perf_counter()
            stats = algo.round(data['private'], public, cfg['seed'], rnd)
            elapsed = perf_counter()-before
            relations = algo.last_relations
            require(all(len(order) == budget for order in stats['public_orders']), 'Student budget changed')
            counts = np.sum(relations, axis=0)
            require(np.array_equal(counts, algo.protocol.counts), f'Round {rnd}: wrong aggregate')
            require(all(np.array_equal(target, counts/len(relations)) for target in stats['consumed']),
                    f'Round {rnd}: wrong student target')
            triggers.update(g.fallback for g in algo.generators if isinstance(g, TrainingGuard) and g.fallback)
            rows.append(dict(round=rnd, seconds=elapsed, **{key: stats[key] for key in STAGES},
                             endpoints=sum(stats['endpoints']), head=algo.state_digest(), traffic=algo.traffic(),
                             relations=[np.packbits(rel).tobytes().hex() for rel in relations]))
            if rnd in ticks:
                evaluation_seconds += evaluate(rnd)
                sample_power()
    require(model_digest(models) == ref['selected_model_digest'], 'Frozen encoder changed')
    suspend_end = suspend_clock()
    return dict(rows=rows, quality=quality, setup_seconds=setup_seconds, load_seconds=load_seconds,
                evaluation_seconds=evaluation_seconds, worker_seconds=perf_counter()-started,
                shared_ae_seconds=meta['common_ae_seconds'], selection_seconds=preparation['selection_seconds'],
                cache_bytes=algo.cache_bytes(), triggers=dict(triggers), power=dict(power),
                suspend_seconds=None if None in (suspend_start, suspend_end) else max(0., suspend_end-suspend_start))
