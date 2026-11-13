"""E28 engine snapshot with only the private-update import replaced.

The original file remains frozen for historical source verification.
"""
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np
from threadpoolctl import threadpool_info

from experiments.quantity_heterogeneity import data as quantity_data
from experiments.public_scaling.data import Prepared as CorePrepared
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.engine import evaluate, heads_digest, METHODS as MODES
from experiments.public_scaling.certification import RelationGenerator
from experiments.private_workload.engine import WorkloadMethod
from experiments.private_workload.sampling import subset_digest
from .training import private_workload_epoch
from experiments.private_workload.student import update, schedule_digest
from experiments.local_public_lr import probes
from experiments.local_public_lr.design import BRANCHES, PROBE_SIZES, public_client_weights


def _snapshot(head):
    from types import SimpleNamespace
    return SimpleNamespace(w=head.w.copy(), b=head.b.copy())


def _head_digest(head):
    h = hashlib.sha256()
    h.update(np.asarray(head.w).tobytes())
    h.update(np.asarray(head.b).tobytes())
    return h.hexdigest()


def _load_verified_data(directory, cfg, fixture):
    """Load a verified STL cache without misusing CorePrepared's MNIST fixture flag."""
    metadata = json.loads((Path(directory) / 'prepared.json').read_text(encoding='utf-8'))
    expected_dataset = 'STL-10 fixture' if fixture else 'STL-10'
    if metadata.get('dataset') != expected_dataset:
        raise ValueError('Prepared dataset identity differs from fixture mode')
    # quantity_data.verify has already authenticated the cache and the official
    # STL-10 source checksums. CorePrepared's allow_test_fixture flag only
    # permits non-MNIST data, so initialize the same fields directly here.
    prepared = CorePrepared.__new__(CorePrepared)
    prepared.directory = Path(directory)
    prepared.metadata = metadata
    prepared.seed = metadata['seed']
    prepared.edges = make_graph(cfg.samples, cfg.degree, prepared.seed)
    prepared.public_ids = np.load(prepared.directory / 'public_ids.npy', allow_pickle=False)[:cfg.samples]
    prepared.private, prepared.public, prepared.pseudo, prepared.test = [], [], [], []
    for client, width in enumerate(cfg.dimensions):
        load = lambda suffix: np.load(prepared.directory / f'client_{client}_{suffix}.npy',
                                      mmap_mode='r', allow_pickle=False)
        prepared.private.append(load('private'))
        public_mapping = load('public')
        if public_mapping.shape != (cfg.public_pool, width):
            raise ValueError('Public pool feature shape mismatch')
        prepared.public.append(np.array(public_mapping[:cfg.samples], dtype=np.float64))
        public_mapping._mmap.close()
        prepared.pseudo.append(load('pseudo'))
        prepared.test.append(load('test'))
        if prepared.public[-1].shape != (cfg.samples, width):
            raise ValueError('Public feature shape mismatch')
        if prepared.private[-1].shape[1] != width or len(prepared.pseudo[-1]) != len(prepared.private[-1]):
            raise ValueError('Private feature/pseudolabel shape mismatch')
    prepared.test_labels = np.load(prepared.directory / 'test_labels.npy', allow_pickle=False)
    return prepared


def _private_probe(data, client, head):
    return probes.prediction_summary(data.private[client], head, data.pseudo[client])


def _public_probe(data, client, head, indices):
    return probes.prediction_summary(data.public[client][indices], head)


def _initial_diagnostics(data, trainer, indices, weights, enabled):
    clients = []
    for client, head in enumerate(trainer.heads):
        pseudo = np.asarray(data.pseudo[client])
        item = dict(client=client, private_capacity=int(len(data.private[client])),
                    fixed_pseudo_histogram=np.bincount(pseudo, minlength=trainer.config.classes).astype(int).tolist(),
                    head_digest=_head_digest(head), actual_public_weight=float(weights[client]),
                    actual_public_effective_lr=float(trainer.config.head_lr * weights[client]))
        if enabled:
            item.update(private_prediction=_private_probe(data, client, head),
                        public_probe_prediction=_public_probe(data, client, head, indices))
        clients.append(item)
    return dict(round=0, clients=clients)


def _step(trainer, rnd, branch, public_weights, probe_indices, enable_probes):
    data = trainer.data
    cfg = trainer.config
    start = perf_counter()
    probe_elapsed = 0.0
    t = perf_counter()
    heads_t0 = [_snapshot(h) for h in trainer.heads]
    digests_t0 = [_head_digest(h) for h in trainer.heads]
    diagnostics = []
    if enable_probes:
        for client, head in enumerate(trainer.heads):
            diagnostics.append(dict(client=client, T0=dict(
                private=_private_probe(data, client, head),
                public=_public_probe(data, client, head, probe_indices),
                head_digest=digests_t0[client])))
    probe_elapsed += perf_counter() - t

    stage = perf_counter()
    losses, private_points, subsets = [], 0, []
    for client, head in enumerate(trainer.heads):
        loss, n, indices = private_workload_epoch(
            head, data.private[client], data.pseudo[client], cfg, data.seed,
            client, rnd, trainer.spec.private_limit)
        losses.append(loss)
        private_points += n
        subsets.append(indices)
    private_s = perf_counter() - stage

    t = perf_counter()
    heads_t1 = [_snapshot(h) for h in trainer.heads]
    digests_t1 = [_head_digest(h) for h in trainer.heads]
    if enable_probes:
        for client, head in enumerate(trainer.heads):
            diagnostics[client]['T1'] = dict(
                private=_private_probe(data, client, head),
                public=_public_probe(data, client, head, probe_indices),
                head_digest=digests_t1[client],
                private_update_delta=probes.head_distance(heads_t0[client], heads_t1[client]))
    probe_elapsed += perf_counter() - t

    stage = perf_counter()
    relations, snapshots, statistics = [], [], []
    for client, head in enumerate(trainer.heads):
        w, b = head.w.copy(), head.b.copy()
        snapshots.append((w, b))
        if rnd == 1:
            generator = RelationGenerator(data.public[client], w, b, data.edges, MODES['B'])
            trainer.generators.append(generator)
            relations.append(generator.initial_relations)
            del generator.initial_relations
            statistics.append(dict(forward_endpoints=cfg.samples,
                                   certified_edges_before_refresh=0,
                                   candidate_entries=cfg.samples * cfg.classes))
        else:
            relation, stats = trainer.generators[client].generate(w, b)
            relations.append(relation)
            statistics.append(stats)
    generation_s = perf_counter() - stage

    stage = perf_counter()
    traffic = trainer.protocol.exchange(relations)
    targets = [counts.astype(np.float64) / len(trainer.heads)
               for counts in trainer.protocol.client_counts]
    exchange_s = perf_counter() - stage

    public_losses, public_points, orders = [], 0, []
    stage = perf_counter()
    for client, head in enumerate(trainer.heads):
        # Keep the trainer's main spec untouched. Each call gets a local copy
        # with only the effective public weight changed for this client.
        client_config = replace(cfg, public_weight=public_weights[client])
        client_spec = replace(trainer.spec, config=client_config)
        loss, count, order = update(head, data.public[client], data.edges, targets[client],
                                    client_spec, data.seed, client, rnd)
        public_losses.append(loss)
        public_points += count
        orders.append(order)
    public_s = perf_counter() - stage

    t = perf_counter()
    heads_t2 = [_snapshot(h) for h in trainer.heads]
    digests_t2 = [_head_digest(h) for h in trainer.heads]
    if enable_probes:
        for client, head in enumerate(trainer.heads):
            diagnostics[client]['T2'] = dict(
                private=_private_probe(data, client, head),
                public=_public_probe(data, client, head, probe_indices),
                head_digest=digests_t2[client],
                public_update_delta=probes.head_distance(heads_t1[client], heads_t2[client]))
    probe_elapsed += perf_counter() - t
    for client, item in enumerate(diagnostics):
        item['private_update_loss'] = float(losses[client])
        item['public_update_loss'] = float(public_losses[client])
        item['positive_relation_fraction_T1'] = float(np.mean(relations[client]))
        item['teacher_relation_sha256_T1'] = hashlib.sha256(
            np.asarray(relations[client], dtype=np.uint8).tobytes()).hexdigest()
        selected = subsets[client]
        private_order_hashes = []
        for epoch in range(cfg.private_epochs):
            order = np.random.default_rng(np.random.SeedSequence(
                [int(data.seed), 401, client, rnd, epoch])).permutation(len(selected))
            actual_order = selected[order]
            private_order_hashes.append(hashlib.sha256(
                np.asarray(actual_order, dtype='<u8').tobytes()).hexdigest())
        item['private_order_sha256'] = private_order_hashes
        item['public_order_sha256'] = hashlib.sha256(
            np.asarray(orders[client], dtype='<u4').tobytes()).hexdigest()
        item['actual_public_weight'] = float(public_weights[client])
        item['actual_public_effective_lr'] = float(cfg.head_lr * public_weights[client])

    pipeline_s = max(0.0, perf_counter() - start - probe_elapsed)
    row = dict(method='B', round=rnd, private_seconds=private_s,
        generation_seconds=generation_s, exchange_seconds=exchange_s,
        public_seconds=public_s, pipeline_seconds=pipeline_s,
        private_loss=float(np.mean(losses)), public_loss=float(np.mean(public_losses)),
        private_forward_endpoints=private_points, student_forward_endpoints=public_points,
        private_samples_per_client=[len(x) for x in subsets],
        private_subset_digest=subset_digest(subsets),
        private_subset_pseudo_histograms=[
            np.bincount(data.pseudo[c][idx], minlength=cfg.classes).astype(int).tolist()
            for c, idx in enumerate(subsets)],
        private_optimizer_steps=sum((len(x) + cfg.private_batch - 1) // cfg.private_batch
                                    for x in subsets) * cfg.private_epochs,
        public_optimizer_steps=trainer.spec.effective_steps * len(trainer.heads),
        public_edges_consumed=sum(map(len, orders)),
        public_schedule_digest=schedule_digest(orders),
        positive_relation_fraction=float(np.mean(relations)),
        committed_counts_digest=hashlib.sha256(trainer.protocol.counts.astype('<u8').tobytes()).hexdigest(),
        received_counts_digests=[hashlib.sha256(v.astype('<u8').tobytes()).hexdigest()
                                 for v in trainer.protocol.client_counts],
        teacher_forward_endpoints=sum(s['forward_endpoints'] for s in statistics),
        certified_edges_before_refresh=sum(s['certified_edges_before_refresh'] for s in statistics),
        client_statistics=statistics, traffic=traffic,
        head_digest_after_public=heads_digest(trainer.heads),
        persistent_method_array_bytes=trainer.persistent_bytes(),
        probe_seconds=probe_elapsed)
    return row, relations, snapshots, orders, dict(round=rnd, clients=diagnostics)


def run(directory, spec, *, branch, fixture=False, progress=True, enable_probes=True):
    """Train the B method with the registered per-client public LR branch."""
    if branch not in BRANCHES:
        raise ValueError(f'Unknown branch: {branch}')
    spec.validate()
    cfg = spec.config
    if any(p['num_threads'] != cfg.threads for p in threadpool_info()
           if p['user_api'] == 'blas'):
        raise ValueError('Unexpected BLAS threads')
    directory = Path(directory)
    meta = json.loads((directory / 'prepared.json').read_text(encoding='utf-8'))
    quantity_data.verify(directory, cfg, meta['seed'], meta['partition'],
                         profile='strong', fixture=fixture)
    started = perf_counter()
    prepared = _load_verified_data(directory, cfg, fixture)
    loading = perf_counter() - started
    try:
        trainer = WorkloadMethod('B', prepared, spec)
        trainer.spec = spec
        public_weights = public_client_weights(branch, len(cfg.dimensions))
        probe_size = PROBE_SIZES['smoke' if fixture else 'full']
        probe_meta = probes.manifest(prepared.seed, prepared.public_ids, probe_size)
        probe_indices = np.asarray(probe_meta['local_indices'], dtype=np.int64)
        initial = heads_digest(trainer.heads)
        probe_start = perf_counter()
        initial_diagnostics = _initial_diagnostics(prepared, trainer, probe_indices,
                                                  public_weights, enable_probes)
        initial_probe_seconds = perf_counter() - probe_start
        diagnostic_records, round_rows, quality = [], [], []
        eval_s = 0.0
        for rnd in range(1, cfg.rounds + 1):
            row, relations, snapshots, orders, diagnostic = _step(
                trainer, rnd, branch, public_weights, probe_indices, enable_probes)
            round_rows.append(row)
            if enable_probes:
                diagnostic_records.append(diagnostic)
            if rnd % cfg.eval_every == 0 or rnd == cfg.rounds:
                t = perf_counter()
                quality.append(dict(round=rnd, method='B', **evaluate(trainer.heads, prepared, cfg)))
                eval_s += perf_counter() - t
            if progress and (rnd % 10 == 0 or rnd == cfg.rounds):
                print(f'  {spec.case_id} branch={branch} seed={prepared.seed}: {rnd}/{cfg.rounds}', flush=True)

        pipeline = trainer.initialization_seconds + sum(r['pipeline_seconds'] for r in round_rows)
        generation = sum(r['generation_seconds'] for r in round_rows)
        summary = dict(initialization_seconds=trainer.initialization_seconds,
            head_pipeline_seconds=pipeline,
            with_shared_preparation_seconds=meta['preparation_wall_seconds_excluding_download'] + loading + pipeline,
            **{p + '_seconds': sum(r[p + '_seconds'] for r in round_rows)
               for p in ('private', 'generation', 'exchange', 'public')},
            generation_fraction=generation / pipeline,
            teacher_recompute_fraction=None if cfg.rounds == 1 else
                sum(r['teacher_forward_endpoints'] for r in round_rows[1:]) /
                (cfg.samples * len(cfg.dimensions) * (cfg.rounds - 1)),
            persistent_method_array_bytes=trainer.persistent_bytes(),
            initial_traffic=trainer.initial_traffic, traffic=trainer.protocol.traffic.snapshot(),
            public_optimizer_steps=sum(r['public_optimizer_steps'] for r in round_rows),
            student_forward_endpoints=sum(r['student_forward_endpoints'] for r in round_rows),
            private_optimizer_steps=sum(r['private_optimizer_steps'] for r in round_rows),
            private_forward_endpoints=sum(r['private_forward_endpoints'] for r in round_rows),
            private_samples_per_client=round_rows[0]['private_samples_per_client'],
            final_head_digest=heads_digest(trainer.heads), final_metrics=quality[-1] if quality else None,
            probe_seconds=initial_probe_seconds + sum(r['probe_seconds'] for r in round_rows),
            initial_probe_seconds=initial_probe_seconds)
        return dict(seed=prepared.seed, partition=meta['partition'], profile='strong', branch=branch,
            dataset=meta['dataset'], config=cfg.json(), spec=spec.json(), case_id=spec.case_id,
            public_client_weights=public_weights,
            initial_head_digest=initial,
            graph_sha256=hashlib.sha256(prepared.edges.astype('<u4').tobytes()).hexdigest(),
            prepared_directory=str(prepared.directory.resolve()),
            common_preparation_seconds=meta['preparation_wall_seconds_excluding_download'],
            shared_loading_seconds=loading, summary={'B': summary}, round_records=round_rows,
            metrics=quality, initial_diagnostics=initial_diagnostics,
            diagnostic_records=diagnostic_records, probe_manifest=probe_meta,
            probes_enabled=enable_probes,
            validation=dict(enabled=False, mismatches=None, relation_comparisons=0,
                            candidate_membership_comparisons=0,
                            evaluation_seconds_excluded=eval_s),
            process=dict(pid=os.getpid()))
    finally:
        prepared.close()
