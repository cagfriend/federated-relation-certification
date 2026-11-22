"""Screen the added computation on real archived E42 teacher snapshots."""

from statistics import mean

from experiments.public_scaling.endpoint_bias import EndpointBiasGenerator
from experiments.snapshot_certification_timing.design import read, require, sealed, sha
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import raw_sha
from ..bias_resources.worker import generate, load_trace, non_timing
from ..confirmation.run import trace_record
from .guard import GuardedGenerator


def references(source):
    path = source/'manifest.json'
    identity = sha(path)
    complete = sealed(source/'completed.json')
    require(read(path)['preset'] == 'full' and complete['manifest'] == identity, 'Need completed E42 inputs')
    entries = []
    for seed in (2022, 2023):
        for partition in ('iid', 'dirichlet_0.1'):
            case = dict(seed=seed, partition=partition, public_size=4096)
            cell = cell_id(case)
            payload, ref = trace_record(source, case, identity, 'full')
            json_path = payload.with_suffix('.json')
            require(complete['traces'][cell] == sha(json_path) and raw_sha(payload) == ref['payload_sha256'],
                    f'Changed E42 trace: {cell}')
            entries.append((cell, payload, ref))
    return entries


def screen(entries):
    pairs, rounds = [], []
    for i, (cell, payload, ref) in enumerate(entries):
        cfg = ref['cfg']
        edges, packed, arrays = load_trace(payload, cfg)
        signatures, cell_pairs = {}, []
        for repeat in range(1, 5):
            order = ('current', 'combined') if (i + repeat) % 2 else ('combined', 'current')
            costs = {}
            for method in order:
                guards = []

                def guarded(x, w, b, graph):
                    model = GuardedGenerator(x, w, b, graph, interval=True, dense=True)
                    guards.append(model)
                    return model

                factory = EndpointBiasGenerator if method == 'current' else guarded
                run = generate(factory, arrays, edges, packed, cfg)
                signature = non_timing(run)
                require(method not in signatures or signature == signatures[method],
                        f'Non-timing result changed during replay: {cell} {method}')
                signatures[method] = signature
                costs[method] = dict(
                    seconds=sum(row['seconds'] for row in run['rows']),
                    endpoints=sum(sum(row['endpoints']) for row in run['rows']),
                    scoring_macs=sum(row['scoring_macs'] for row in run['rows']),
                    mismatches=sum(sum(row['mismatches']) for row in run['rows']),
                    cache_bytes=run['cache_bytes'],
                    scale_client_rounds=sum(g.scale_rounds for g in guards),
                    rebuild_client_rounds=sum(g.rebuild_rounds for g in guards),
                )
                rounds.extend(dict(cell=cell, repeat=repeat, method=method, **row) for row in run['rows'])
            result = dict(cell=cell, repeat=repeat, order='→'.join(order))
            result.update({f'{method}_{key}': value for method, cost in costs.items() for key, value in cost.items()})
            cell_pairs.append(result)
        current = mean(row['current_seconds'] for row in cell_pairs)
        combined = mean(row['combined_seconds'] for row in cell_pairs)
        print(f'Replay {cell}: four pairs, added generation time {100*(combined/current - 1):+.2f}%', flush=True)
        pairs.extend(cell_pairs)
    # The method order alternates, while CSV rows keep stable columns.
    return pairs, rounds
