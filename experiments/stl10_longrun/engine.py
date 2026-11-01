"""B-only long-horizon engine: frozen transfer training, richer checkpoints.

Reuses the private_workload WorkloadMethod exactly as the STL-10 transfer
engine does; only orchestration differs (checkpoint set, private pseudo-label
fit probe, no oracle audit -- B is the reference computation, and exactness
is anchored against the historical step-8 B run by run.py).
"""
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from threadpoolctl import threadpool_info

from experiments.public_scaling.data import Prepared as CorePrepared
from experiments.public_scaling.engine import evaluate, heads_digest
from experiments.private_workload.engine import WorkloadMethod
from experiments.stl10_diagnostics.probes import probe
from experiments.stl10_transfer.data import verify

from .design import S2_FROM_ROUND, checkpoints


def _checkpoint(round_number, method, data, config, edge_fraction):
    metrics = evaluate(method.heads, data, config)
    fits = [probe(head, data.private[client], pseudo=data.pseudo[client])['pseudo_accuracy']
            for client, head in enumerate(method.heads)]
    clients = metrics['clients']
    return dict(round=round_number, clients=clients, mean=metrics['mean'],
                single_cluster_clients=sum(c['occupied_clusters'] == 1 for c in clients),
                dominant_99_clients=sum(c['largest_cluster_fraction'] >= 0.99 for c in clients),
                mean_largest_cluster_fraction=float(np.mean([c['largest_cluster_fraction'] for c in clients])),
                private_pseudo_fit_mean=float(np.mean(fits)),
                teacher_edge_fraction=edge_fraction)


def run(directory, spec, *, fixture=False):
    spec.validate()
    cfg = spec.config
    if any(x['num_threads'] != cfg.threads for x in threadpool_info() if x['user_api'] == 'blas'):
        raise ValueError('Unexpected BLAS threads')
    meta = json.loads((Path(directory) / 'prepared.json').read_text(encoding='utf-8'))
    verify(directory, cfg, meta['seed'], meta['partition'], fixture=fixture)
    if meta['dataset'] != ('STL-10 fixture' if fixture else 'STL-10'):
        raise ValueError('Dataset identity mismatch')
    t = perf_counter()
    data = CorePrepared(directory, cfg, allow_test_fixture=True)
    loading = perf_counter() - t
    try:
        m = WorkloadMethod('B', data, spec)
        initial = heads_digest(m.heads)
        wanted = set(checkpoints(cfg.rounds))
        records, cps, eval_seconds = [], [], 0.0
        t = perf_counter()
        cps.append(_checkpoint(0, m, data, cfg, None))
        eval_seconds += perf_counter() - t
        for rnd in range(1, cfg.rounds + 1):
            row, relations, snapshots, orders = m.step(rnd)
            records.append(row)
            if any(h != row['committed_counts_digest'] for h in row['received_counts_digests']):
                raise AssertionError('Received target mismatch')
            if rnd in wanted:
                t = perf_counter()
                cps.append(_checkpoint(rnd, m, data, cfg, row['positive_relation_fraction']))
                eval_seconds += perf_counter() - t
        events = [dict(round=c['round'], single_cluster_clients=c['single_cluster_clients'],
                       dominant_99_clients=c['dominant_99_clients'],
                       warning_only=c['round'] < S2_FROM_ROUND)
                  for c in cps if c['single_cluster_clients'] or c['dominant_99_clients']]
        pipeline = m.initialization_seconds + sum(r['pipeline_seconds'] for r in records)
        summary = dict(initialization_seconds=m.initialization_seconds, head_pipeline_seconds=pipeline,
                       **{p + '_seconds': sum(r[p + '_seconds'] for r in records)
                          for p in ('private', 'generation', 'exchange', 'public')},
                       public_optimizer_steps=sum(r['public_optimizer_steps'] for r in records),
                       private_optimizer_steps=sum(r['private_optimizer_steps'] for r in records),
                       final_head_digest=heads_digest(m.heads), final_metrics=cps[-1]['mean'])
        return dict(seed=data.seed, dataset=meta['dataset'], config=cfg.json(), spec=spec.json(),
                    case_id=spec.case_id, rounds=cfg.rounds, public_steps=spec.steps,
                    initial_head_digest=initial,
                    graph_sha256=hashlib.sha256(data.edges.astype('<u4').tobytes()).hexdigest(),
                    prepared_directory=str(data.directory.resolve()),
                    common_preparation_seconds=meta['preparation_wall_seconds_excluding_download'],
                    shared_loading_seconds=loading, summary={'B': summary},
                    round_records=records, checkpoints=cps, events=events,
                    validation=dict(enabled=False, mismatches=0,
                                    reason='B is the reference computation; no per-round oracle audit. '
                                           'Exactness is anchored on the historical step-8 B run.'),
                    evaluation_seconds_excluded=eval_seconds, process=dict(pid=os.getpid()))
    finally:
        data.close()
