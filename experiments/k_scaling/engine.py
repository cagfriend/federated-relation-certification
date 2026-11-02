"""STL-10 output-cluster scaling using the frozen K=10 feature cache."""
import hashlib
import os
from dataclasses import replace
from pathlib import Path
from time import perf_counter

import numpy as np
from threadpoolctl import threadpool_info

from experiments.public_scaling.data import Prepared as CorePrepared
from experiments.public_scaling.engine import audit, evaluate, heads_digest
from experiments.private_workload.engine import WorkloadMethod
from experiments.private_workload.student import Coverage
from experiments.stl10_transfer.data import verify


def run(base_directory, spec, pseudo_paths, *, fixture=False, validate=True,
        metrics=True, progress=False, method="B"):
    """Train one K case while reusing K=10 frozen representations.

    ``pseudo_paths`` is ordered by client and contains the K-specific private
    pseudolabel arrays. The base cache is verified against its original K=10
    preparation configuration before those arrays are substituted.
    """
    spec.validate()
    cfg = spec.config
    if method not in ("B", "E", "D"):
        raise ValueError("Unknown method")
    if any(p["num_threads"] != cfg.threads for p in threadpool_info()
           if p["user_api"] == "blas"):
        raise ValueError("Unexpected BLAS threads")
    if len(pseudo_paths) != len(cfg.dimensions):
        raise ValueError("Expected one pseudolabel path per client")

    basecfg = replace(cfg, classes=10)
    import json
    base_directory = Path(base_directory)
    meta = json.loads((base_directory / "prepared.json").read_text(encoding="utf-8"))
    verify(base_directory, basecfg, meta["seed"], meta["partition"], fixture=fixture)

    started = perf_counter()
    data = CorePrepared(base_directory, basecfg, allow_test_fixture=True)
    loading = perf_counter() - started
    replacements = []
    try:
        for client, path in enumerate(pseudo_paths):
            z = np.load(path, mmap_mode="r", allow_pickle=False)
            if z.shape != data.pseudo[client].shape:
                mapping = getattr(z, "_mmap", None)
                if mapping is not None:
                    mapping.close()
                raise ValueError(f"Client {client} pseudolabel shape mismatch")
            if z.dtype.kind not in "iu" or np.any(z < 0) or np.any(z >= cfg.classes):
                mapping = getattr(z, "_mmap", None)
                if mapping is not None:
                    mapping.close()
                raise ValueError(f"Client {client} pseudolabel outside [0, K)")
            replacements.append(z)
        # Close the original K=10 mappings before replacing references.
        for old in data.pseudo:
            mapping = getattr(old, "_mmap", None)
            if mapping is not None:
                mapping.close()
        data.pseudo = replacements
        replacements = []  # ownership now belongs to CorePrepared.close()
        loading = perf_counter() - started

        trainer = WorkloadMethod(method, data, spec)
        initial = heads_digest(trainer.heads)
        observer = Coverage(len(cfg.dimensions), data.edges, cfg.samples) if validate else None
        rr, quality, coverage_rows = [], [], []
        checks = members = 0
        audit_s = eval_s = 0.0
        for rnd in range(1, cfg.rounds + 1):
            row, relations, snapshots, orders = trainer.step(rnd)
            rr.append(row)
            if any(h != row["committed_counts_digest"] for h in row["received_counts_digests"]):
                raise AssertionError("Received target mismatch")
            if validate:
                t = perf_counter()
                a, b = audit(trainer, relations, snapshots, data)
                checks += a
                # The B oracle path has no candidate matrix to check.
                if method != "B":
                    members += b
                coverage_rows.append(dict(round=rnd, **observer.observe(orders)))
                audit_s += perf_counter() - t
            if metrics and (rnd % cfg.eval_every == 0 or rnd == cfg.rounds):
                t = perf_counter()
                quality.append(dict(round=rnd, method=method,
                                    **evaluate(trainer.heads, data, cfg)))
                eval_s += perf_counter() - t
            if progress and (rnd % 10 == 0 or rnd == cfg.rounds):
                print(f"  {spec.case_id} seed={data.seed}: {rnd}/{cfg.rounds}", flush=True)

        pipeline = trainer.initialization_seconds + sum(r["pipeline_seconds"] for r in rr)
        generation = sum(r["generation_seconds"] for r in rr)
        summary = dict(initialization_seconds=trainer.initialization_seconds,
            head_pipeline_seconds=pipeline,
            with_shared_preparation_seconds=meta["preparation_wall_seconds_excluding_download"] + loading + pipeline,
            **{p + "_seconds": sum(r[p + "_seconds"] for r in rr)
               for p in ("private", "generation", "exchange", "public")},
            generation_fraction=generation / pipeline,
            teacher_recompute_fraction=None if cfg.rounds == 1 else
                sum(r["teacher_forward_endpoints"] for r in rr[1:]) /
                (cfg.samples * len(cfg.dimensions) * (cfg.rounds - 1)),
            persistent_method_array_bytes=trainer.persistent_bytes(),
            initial_traffic=trainer.initial_traffic, traffic=trainer.protocol.traffic.snapshot(),
            public_optimizer_steps=sum(r["public_optimizer_steps"] for r in rr),
            student_forward_endpoints=sum(r["student_forward_endpoints"] for r in rr),
            private_optimizer_steps=sum(r["private_optimizer_steps"] for r in rr),
            private_forward_endpoints=sum(r["private_forward_endpoints"] for r in rr),
            private_samples_per_client=rr[0]["private_samples_per_client"],
            final_head_digest=heads_digest(trainer.heads),
            final_metrics=quality[-1] if quality else None)
        return dict(seed=data.seed, dataset=meta["dataset"], config=cfg.json(), spec=spec.json(),
            case_id=spec.case_id, classes=cfg.classes, validate=validate, metrics_enabled=metrics,
            initial_head_digest=initial,
            graph_sha256=hashlib.sha256(data.edges.astype("<u4").tobytes()).hexdigest(),
            prepared_directory=str(data.directory.resolve()),
            common_preparation_seconds=meta["preparation_wall_seconds_excluding_download"],
            shared_loading_seconds=loading, summary={method: summary}, round_records=rr,
            metrics=quality, coverage=observer.snapshot() if observer else None,
            coverage_records=coverage_rows,
            validation=dict(enabled=validate, mismatches=0 if validate else None,
                relation_comparisons=checks, candidate_membership_comparisons=members,
                audit_and_coverage_seconds_excluded=audit_s, evaluation_seconds_excluded=eval_s),
            process=dict(pid=os.getpid()))
    finally:
        for array in replacements:
            mapping = getattr(array, "_mmap", None)
            if mapping is not None:
                mapping.close()
        data.close()
