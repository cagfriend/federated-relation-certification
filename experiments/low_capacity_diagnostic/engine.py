"""Instrumented strong-profile B baseline and low-capacity interventions."""
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

import numpy as np
from threadpoolctl import threadpool_info

from experiments.quantity_heterogeneity import data as quantity_data
from experiments.public_scaling.data import Prepared as CorePrepared
from experiments.public_scaling.engine import evaluate, heads_digest, METHODS as MODES
from experiments.public_scaling.generation import make_generator
from experiments.private_workload.engine import WorkloadMethod
from experiments.private_workload.sampling import private_workload_epoch, subset_digest
from experiments.private_workload.student import update, schedule_digest
from . import probes


def _snapshot(head):
    return SimpleNamespace(w=head.w.copy(), b=head.b.copy())


def _head_digest(head):
    h = hashlib.sha256()
    h.update(np.asarray(head.w).tobytes())
    h.update(np.asarray(head.b).tobytes())
    return h.hexdigest()


def _private_probe(prepared, client, head):
    return probes.prediction_summary(prepared.private[client], head,
                                     prepared.pseudo[client])


def _public_probe(prepared, client, head, indices):
    return probes.prediction_summary(prepared.public[client][indices], head)


def _initial_diagnostics(prepared, trainer, indices, enabled):
    clients = []
    for c, head in enumerate(trainer.heads):
        pseudo = np.asarray(prepared.pseudo[c])
        counts = np.bincount(pseudo, minlength=trainer.config.classes).astype(np.int64)
        item = dict(client=c, private_capacity=int(len(prepared.private[c])),
                    fixed_pseudo_histogram=counts.tolist(),
                    head_digest=_head_digest(head))
        if enabled:
            item.update(private_prediction=_private_probe(prepared, c, head),
                        public_probe_prediction=_public_probe(prepared, c, head, indices))
        clients.append(item)
    return dict(round=0, clients=clients)


def _step(trainer, rnd, branch, probe_indices, enable_probes):
    """Same B workload streams and ordering, with read-only T0/T1/T2 probes."""
    data = trainer.data
    cfg = trainer.config
    start = perf_counter()
    probe_elapsed = 0.0
    t = perf_counter()
    heads_t0 = [_snapshot(h) for h in trainer.heads]
    digests_t0 = [_head_digest(h) for h in trainer.heads]
    diagnostics = []
    if enable_probes:
        for c, h in enumerate(trainer.heads):
            diagnostics.append(dict(client=c, T0=dict(
                private=_private_probe(data, c, h),
                public=_public_probe(data, c, h, probe_indices),
                head_digest=digests_t0[c])))
    probe_elapsed += perf_counter() - t

    # Preserve WorkloadMethod's private workload call order and isolated RNG.
    stage = perf_counter()
    losses, private_points, subsets = [], 0, []
    for c, h in enumerate(trainer.heads):
        loss, n, indices = private_workload_epoch(
            h, data.private[c], data.pseudo[c], cfg, data.seed, c, rnd,
            trainer.spec.private_limit)
        losses.append(loss)
        private_points += n
        subsets.append(indices)
    private_s = perf_counter() - stage

    t = perf_counter()
    heads_t1 = [_snapshot(h) for h in trainer.heads]
    digests_t1 = [_head_digest(h) for h in trainer.heads]
    if enable_probes:
        for c, h in enumerate(trainer.heads):
            diagnostics[c]['T1'] = dict(
                private=_private_probe(data, c, h),
                public=_public_probe(data, c, h, probe_indices),
                head_digest=digests_t1[c],
                private_update_delta=probes.head_distance(heads_t0[c], heads_t1[c]))
    probe_elapsed += perf_counter() - t

    # This is the teacher snapshot used by the original B implementation.
    stage = perf_counter()
    relations, snapshots, statistics = [], [], []
    for c, h in enumerate(trainer.heads):
        w, b = h.w.copy(), h.b.copy()
        snapshots.append((w, b))
        if rnd == 1:
            generator = make_generator(data.public[c], w, b, data.edges, MODES['B'])
            trainer.generators.append(generator)
            relations.append(generator.initial_relations)
            del generator.initial_relations
            statistics.append(dict(forward_endpoints=cfg.samples,
                                   certified_edges_before_refresh=0,
                                   candidate_entries=cfg.samples * cfg.classes))
        else:
            rel, stat = trainer.generators[c].generate(w, b)
            relations.append(rel)
            statistics.append(stat)
    generation_s = perf_counter() - stage

    stage = perf_counter()
    traffic = trainer.protocol.exchange(relations)
    targets = [counts.astype(np.float64) / len(trainer.heads)
               for counts in trainer.protocol.client_counts]
    exchange_s = perf_counter() - stage

    public_losses, public_points, orders = [], 0, []
    stage = perf_counter()
    if branch == 'private_only':
        orders = [np.empty(0, dtype=np.uint32) for _ in trainer.heads]
    else:
        for c, h in enumerate(trainer.heads):
            loss, n, order = update(h, data.public[c], data.edges, targets[c],
                                    trainer.spec, data.seed, c, rnd)
            public_losses.append(loss)
            public_points += n
            orders.append(order)
    public_s = perf_counter() - stage

    t = perf_counter()
    heads_t2 = [_snapshot(h) for h in trainer.heads]
    digests_t2 = [_head_digest(h) for h in trainer.heads]
    if enable_probes:
        for c, h in enumerate(trainer.heads):
            diagnostics[c]['T2'] = dict(
                private=_private_probe(data, c, h),
                public=_public_probe(data, c, h, probe_indices),
                head_digest=digests_t2[c],
                public_update_delta=probes.head_distance(heads_t1[c], heads_t2[c]))
    probe_elapsed += perf_counter() - t
    t = perf_counter()
    for c in range(len(diagnostics)):
        diagnostics[c]['private_update_loss'] = float(losses[c])
        diagnostics[c]['public_update_loss'] = (None if branch == 'private_only'
                                                else float(public_losses[c]))
        diagnostics[c]['positive_relation_fraction_T1'] = float(np.mean(relations[c]))
        diagnostics[c]['teacher_relation_sha256_T1'] = hashlib.sha256(
            np.asarray(relations[c], dtype=np.uint8).tobytes()).hexdigest()
        diagnostics[c]['private_order_sha256'] = [hashlib.sha256(
            np.asarray(np.random.default_rng(np.random.SeedSequence(
                [int(data.seed), 401, c, rnd, epoch])).permutation(len(data.private[c])),
                dtype='<u8').tobytes()).hexdigest() for epoch in range(cfg.private_epochs)]
        diagnostics[c]['public_order_sha256'] = hashlib.sha256(
            np.asarray(orders[c], dtype='<u4').tobytes()).hexdigest()
    probe_elapsed += perf_counter() - t

    # Keep the frozen training row schema and counts. Probe work is separate
    # from the instrumented training timer so it cannot be mistaken for method cost.
    pipeline_s = max(0.0, perf_counter() - start - probe_elapsed)
    row = dict(method='B', round=rnd, private_seconds=private_s,
        generation_seconds=generation_s, exchange_seconds=exchange_s,
        public_seconds=public_s, pipeline_seconds=pipeline_s,
        private_loss=float(np.mean(losses)),
        public_loss=None if branch == 'private_only' else float(np.mean(public_losses)),
        private_forward_endpoints=private_points,
        student_forward_endpoints=public_points,
        private_samples_per_client=[len(x) for x in subsets],
        private_subset_digest=subset_digest(subsets),
        private_subset_pseudo_histograms=[
            np.bincount(data.pseudo[c][idx], minlength=cfg.classes).astype(int).tolist()
            for c, idx in enumerate(subsets)],
        private_optimizer_steps=sum((len(x) + cfg.private_batch - 1) // cfg.private_batch
                                    for x in subsets) * cfg.private_epochs,
        public_optimizer_steps=0 if branch == 'private_only' else trainer.spec.effective_steps * len(trainer.heads),
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


def run(directory, spec, *, branch, fixture=False, progress=True,
        enable_probes=True):
    """Run one B-only diagnostic branch with read-only diagnostic probes."""
    if branch not in ('baseline', 'private_only', 'low_lr'):
        raise ValueError(f'Unknown diagnostic branch: {branch}')
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
    # The shared loader historically names this flag after fixtures. Official
    # STL-10 identity/checksums were validated above by quantity_data.verify.
    prepared = CorePrepared(directory, cfg, allow_test_fixture=True)
    loading = perf_counter() - started
    try:
        trainer = WorkloadMethod('B', prepared, spec)
        trainer.spec = spec
        probe_size = min(512 if not fixture else 32, cfg.samples)
        probe_meta = probes.manifest(prepared.seed, prepared.public_ids, probe_size)
        probe_indices = np.asarray(probe_meta['local_indices'], dtype=np.int64)
        initial = heads_digest(trainer.heads)
        probe_start = perf_counter()
        initial_diagnostics = _initial_diagnostics(prepared, trainer, probe_indices, enable_probes)
        initial_probe_seconds = perf_counter() - probe_start
        diagnostic_records, round_rows, quality = [], [], []
        eval_s = 0.0
        for rnd in range(1, cfg.rounds + 1):
            row, relations, snapshots, orders, diagnostic = _step(
                trainer, rnd, branch, probe_indices, enable_probes)
            round_rows.append(row)
            if enable_probes:
                diagnostic_records.append(diagnostic)
            if rnd % cfg.eval_every == 0 or rnd == cfg.rounds:
                t = perf_counter()
                quality.append(dict(round=rnd, method='B',
                                    **evaluate(trainer.heads, prepared, cfg)))
                eval_s += perf_counter() - t
            if progress and (rnd % 10 == 0 or rnd == cfg.rounds):
                print(f'  {spec.case_id} branch={branch} seed={prepared.seed}: {rnd}/{cfg.rounds}', flush=True)

        pipeline = trainer.initialization_seconds + sum(r['pipeline_seconds'] for r in round_rows)
        generation = sum(r['generation_seconds'] for r in round_rows)
        summary = dict(
            initialization_seconds=trainer.initialization_seconds,
            head_pipeline_seconds=pipeline,
            with_shared_preparation_seconds=meta['preparation_wall_seconds_excluding_download'] + loading + pipeline,
            **{p + '_seconds': sum(r[p + '_seconds'] for r in round_rows)
               for p in ('private', 'generation', 'exchange', 'public')},
            generation_fraction=(generation / pipeline if pipeline else None),
            teacher_recompute_fraction=None if cfg.rounds == 1 else
                sum(r['teacher_forward_endpoints'] for r in round_rows[1:]) /
                (cfg.samples * len(cfg.dimensions) * (cfg.rounds - 1)),
            persistent_method_array_bytes=trainer.persistent_bytes(),
            initial_traffic=trainer.initial_traffic,
            traffic=trainer.protocol.traffic.snapshot(),
            public_optimizer_steps=sum(r['public_optimizer_steps'] for r in round_rows),
            student_forward_endpoints=sum(r['student_forward_endpoints'] for r in round_rows),
            private_optimizer_steps=sum(r['private_optimizer_steps'] for r in round_rows),
            private_forward_endpoints=sum(r['private_forward_endpoints'] for r in round_rows),
            private_samples_per_client=round_rows[0]['private_samples_per_client'],
            final_head_digest=heads_digest(trainer.heads),
            final_metrics=quality[-1] if quality else None,
            probe_seconds=initial_probe_seconds + sum(r['probe_seconds'] for r in round_rows),
            initial_probe_seconds=initial_probe_seconds)
        return dict(seed=prepared.seed, partition=meta['partition'], profile='strong',
            branch=branch, dataset=meta['dataset'], config=cfg.json(), spec=spec.json(),
            case_id=spec.case_id, initial_head_digest=initial,
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
