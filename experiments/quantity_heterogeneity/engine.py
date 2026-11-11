"""Execution engine for the quantity-heterogeneity study."""
import hashlib
import os
import json
from pathlib import Path
from time import perf_counter

from threadpoolctl import threadpool_info

from experiments.public_scaling.data import Prepared as CorePrepared
from experiments.public_scaling.engine import audit, evaluate, heads_digest
from experiments.private_workload.engine import WorkloadMethod
from experiments.private_workload.student import Coverage
from . import data


def run(directory, spec, method='B', *, profile, fixture=False, memory=False,
        validate=None, metrics=None, progress=False):
    spec.validate()
    cfg = spec.config
    if validate is None:
        validate = not memory
    if metrics is None:
        metrics = not memory
    if method not in ('B', 'E', 'D'):
        raise ValueError('Unknown method')
    if any(p['num_threads'] != cfg.threads for p in threadpool_info()
           if p['user_api'] == 'blas'):
        raise ValueError('Unexpected BLAS threads')
    directory = Path(directory)
    meta = json.loads((directory / 'prepared.json').read_text(encoding='utf-8'))
    data.verify(directory, cfg, meta['seed'], meta['partition'],
                profile=profile, fixture=fixture)

    started = perf_counter()
    prepared = CorePrepared(directory, cfg, allow_test_fixture=True)
    loading = perf_counter() - started
    try:
        trainer = WorkloadMethod(method, prepared, spec)
        initial = heads_digest(trainer.heads)
        observer = Coverage(len(cfg.dimensions), prepared.edges, cfg.samples) if validate else None
        rows, quality, coverage_rows = [], [], []
        checks = members = 0
        audit_s = eval_s = 0.0
        for rnd in range(1, cfg.rounds + 1):
            row, relations, snapshots, orders = trainer.step(rnd)
            rows.append(row)
            if any(h != row['committed_counts_digest'] for h in row['received_counts_digests']):
                raise AssertionError('Received target mismatch')
            if validate:
                t = perf_counter()
                a, b = audit(trainer, relations, snapshots, prepared)
                checks += a
                if method != 'B':
                    members += b
                coverage_rows.append(dict(round=rnd, **observer.observe(orders)))
                audit_s += perf_counter() - t
            if metrics and (rnd % cfg.eval_every == 0 or rnd == cfg.rounds):
                t = perf_counter()
                quality.append(dict(round=rnd, method=method,
                                    **evaluate(trainer.heads, prepared, cfg)))
                eval_s += perf_counter() - t
            if progress and (rnd % 10 == 0 or rnd == cfg.rounds):
                print(f'  {spec.case_id} profile={profile} seed={prepared.seed}: {rnd}/{cfg.rounds}', flush=True)

        pipeline = trainer.initialization_seconds + sum(r['pipeline_seconds'] for r in rows)
        generation = sum(r['generation_seconds'] for r in rows)
        summary = dict(
            initialization_seconds=trainer.initialization_seconds,
            head_pipeline_seconds=pipeline,
            with_shared_preparation_seconds=meta['preparation_wall_seconds_excluding_download'] + loading + pipeline,
            **{p + '_seconds': sum(r[p + '_seconds'] for r in rows)
               for p in ('private', 'generation', 'exchange', 'public')},
            generation_fraction=generation / pipeline,
            teacher_recompute_fraction=None if cfg.rounds == 1 else
                sum(r['teacher_forward_endpoints'] for r in rows[1:]) /
                (cfg.samples * len(cfg.dimensions) * (cfg.rounds - 1)),
            persistent_method_array_bytes=trainer.persistent_bytes(),
            initial_traffic=trainer.initial_traffic,
            traffic=trainer.protocol.traffic.snapshot(),
            public_optimizer_steps=sum(r['public_optimizer_steps'] for r in rows),
            student_forward_endpoints=sum(r['student_forward_endpoints'] for r in rows),
            private_optimizer_steps=sum(r['private_optimizer_steps'] for r in rows),
            private_forward_endpoints=sum(r['private_forward_endpoints'] for r in rows),
            private_samples_per_client=rows[0]['private_samples_per_client'],
            private_samples_by_client=list(rows[0]['private_samples_per_client']),
            final_head_digest=heads_digest(trainer.heads),
            final_metrics=quality[-1] if quality else None)
        return dict(seed=prepared.seed, partition=meta['partition'], profile=profile,
                    regime=f'quantity_{profile}', dataset=meta['dataset'],
                    config=cfg.json(), spec=spec.json(), case_id=spec.case_id,
                    classes=cfg.classes, validate=validate, metrics_enabled=metrics,
                    initial_head_digest=initial,
                    graph_sha256=hashlib.sha256(prepared.edges.astype('<u4').tobytes()).hexdigest(),
                    prepared_directory=str(prepared.directory.resolve()),
                    common_preparation_seconds=meta['preparation_wall_seconds_excluding_download'],
                    shared_loading_seconds=loading, summary={method: summary},
                    round_records=rows, metrics=quality,
                    coverage=observer.snapshot() if observer else None,
                    coverage_records=coverage_rows,
                    validation=dict(enabled=validate, mismatches=0 if validate else None,
                                    relation_comparisons=checks,
                                    candidate_membership_comparisons=members,
                                    audit_and_coverage_seconds_excluded=audit_s,
                                    evaluation_seconds_excluded=eval_s),
                    process=dict(pid=os.getpid()))
    finally:
        prepared.close()
