"""Paired actual SGD training; the existing certificate/protocol are reused."""
import hashlib
import time

import numpy as np
from threadpoolctl import threadpool_info
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

from .certification import RelationGenerator, hard_relations
from .protocol import RelationProtocol
from .head import Head, private_epoch, public_epoch
from .data import Prepared

METHODS = {"B": "full", "E": "point", "D": "relation"}


def heads_digest(heads):
    h = hashlib.sha256()
    for head in heads:
        h.update(head.w.tobytes())
        h.update(head.b.tobytes())
    return h.hexdigest()


def evaluate(heads, prepared, config):
    result = []
    truth = prepared.test_labels.astype(np.int64)
    for client, (head, z) in enumerate(zip(heads, prepared.test)):
        predicted = np.concatenate([(np.asarray(z[i:i + 512], dtype=np.float64) @ head.w.T + head.b).argmax(axis=1)
                                    for i in range(0, len(z), 512)])
        contingency = np.zeros((int(truth.max()) + 1, config.classes), dtype=np.int64)
        np.add.at(contingency, (truth, predicted), 1)
        row, col = linear_sum_assignment(-contingency)
        counts = np.bincount(predicted, minlength=config.classes)
        result.append({"client": client, "width": config.dimensions[client],
                       "nmi": float(normalized_mutual_info_score(truth, predicted)),
                       "ari": float(adjusted_rand_score(truth, predicted)),
                       "acc": float(contingency[row, col].sum() / len(truth)),
                       "occupied_clusters": int(np.count_nonzero(counts)),
                       "largest_cluster_fraction": float(counts.max() / len(truth)),
                       "cluster_counts": counts.tolist()})
    return {"clients": result, "mean": {name: float(np.mean([r[name] for r in result]))
                                         for name in ("nmi", "ari", "acc")}}


class Method:
    def __init__(self, name, prepared, config):
        start = time.perf_counter()
        self.name, self.data, self.config = name, prepared, config
        self.heads = [Head(d, config.classes, prepared.seed, i) for i, d in enumerate(config.dimensions)]
        self.generators = []
        self.protocol = None if name == "Local" else RelationProtocol(
            prepared.edges, config.samples, config.classes, config.dimensions, adaptive=True)
        self.initialization_seconds = time.perf_counter() - start
        self.initial_traffic = {} if self.protocol is None else self.protocol.traffic.snapshot()

    def persistent_bytes(self):
        return (sum(h.w.nbytes + h.b.nbytes for h in self.heads)
                + sum(sum(g.persistent_arrays().values()) for g in self.generators)
                + (0 if self.protocol is None else self.protocol.persistent_bytes()))

    def step(self, round_number):
        start = time.perf_counter()
        losses, private_points = [], 0
        for client, head in enumerate(self.heads):
            loss, points = private_epoch(head, self.data.private[client], self.data.pseudo[client],
                                         self.config, self.data.seed, client, round_number)
            losses.append(loss)
            private_points += points
        private_s = time.perf_counter() - start
        generation_s, exchange_s, public_s = 0.0, 0.0, 0.0
        relations, snapshots, statistics, public_losses = [], [], [], []
        public_points, traffic = 0, {}
        if self.protocol is not None:
            stage = time.perf_counter()
            for client, head in enumerate(self.heads):
                # Snapshot copies are part of teacher-generation cost. Teacher
                # heads remain fixed until all relations/targets are committed.
                w, b = head.w.copy(), head.b.copy()
                snapshots.append((w, b))
                if round_number == 1:
                    generator = RelationGenerator(self.data.public[client], w, b,
                                                  self.data.edges, METHODS[self.name])
                    self.generators.append(generator)
                    relations.append(generator.initial_relations)
                    del generator.initial_relations
                    statistics.append({"forward_endpoints": self.config.samples,
                                       "certified_edges_before_refresh": 0,
                                       "candidate_entries": self.config.samples * self.config.classes})
                else:
                    relation, stat = self.generators[client].generate(w, b)
                    relations.append(relation)
                    statistics.append(stat)
            generation_s = time.perf_counter() - stage
            stage = time.perf_counter()
            traffic = self.protocol.exchange(relations)
            # Each student uses its OWN received committed count vector.
            targets = [counts.astype(np.float64) / len(self.heads) for counts in self.protocol.client_counts]
            exchange_s = time.perf_counter() - stage
            stage = time.perf_counter()
            for client, head in enumerate(self.heads):
                loss, points = public_epoch(head, self.data.public[client], self.data.edges, targets[client],
                                            self.config, self.data.seed, client, round_number)
                public_losses.append(loss)
                public_points += points
            public_s = time.perf_counter() - stage
            # IMPORTANT: do not overwrite generator.previous_weights here.
            # Next generate() compares the next teacher snapshot with the LAST
            # teacher snapshot. Its delta therefore includes public SGD plus
            # the following private SGD, even if their updates cancel.
        total = time.perf_counter() - start
        # Hashes and scalar diagnostics are outside the pipeline stopwatch.
        return {"method": self.name, "round": round_number, "private_seconds": private_s,
                "generation_seconds": generation_s, "exchange_seconds": exchange_s,
                "public_seconds": public_s, "pipeline_seconds": total,
                "private_loss": float(np.mean(losses)),
                "public_loss": None if not public_losses else float(np.mean(public_losses)),
                "private_forward_endpoints": private_points, "student_forward_endpoints": public_points,
                "private_optimizer_steps": sum((len(z) + self.config.private_batch - 1) // self.config.private_batch
                                               for z in self.data.private) * self.config.private_epochs,
                "public_optimizer_steps": (len(self.data.edges) + self.config.public_edge_batch - 1)
                                          // self.config.public_edge_batch * self.config.public_epochs * len(self.heads),
                "positive_relation_fraction": float(np.mean(relations)),
                "teacher_forward_endpoints": sum(s["forward_endpoints"] for s in statistics),
                "certified_edges_before_refresh": sum(s["certified_edges_before_refresh"] for s in statistics),
                "client_statistics": statistics, "traffic": traffic,
                "head_digest_after_public": heads_digest(self.heads),
                "persistent_method_array_bytes": self.persistent_bytes()}, relations, snapshots


def audit(method, relations, snapshots, prepared):
    comparisons, membership = 0, 0
    oracle = []
    for client, ((w, b), relation) in enumerate(zip(snapshots, relations)):
        labels = (prepared.public[client] @ w.T + b).argmax(axis=1)
        exact = hard_relations(labels, prepared.edges)
        if not np.array_equal(exact, relation):
            raise AssertionError(f"{method.name} teacher relation differs from full oracle")
        if not np.array_equal(exact, method.protocol.server_relations[client]):
            raise AssertionError("Uploaded relation was decoded incorrectly")
        oracle.append(exact)
        comparisons += len(exact)
        generator = method.generators[client]
        if generator.mode != "full":
            candidates = generator.candidate_matrix()
            if not np.all(candidates[np.arange(len(labels)), labels]):
                raise AssertionError("Current true winner excluded from candidate set")
            membership += len(labels)
    counts = np.sum(oracle, axis=0, dtype=np.int64)
    if not np.array_equal(counts, method.protocol.counts):
        raise AssertionError("Incorrect aggregate count")
    if any(not np.array_equal(counts, v) for v in method.protocol.client_counts):
        raise AssertionError("A student received different targets")
    return comparisons, membership


def run_seed(directory, config, *, names=tuple(METHODS), validate=True, progress=True, allow_test_fixture=False):
    config.validate()
    pools = threadpool_info()
    if any(p["num_threads"] != config.threads for p in pools if p["user_api"] == "blas"):
        raise ValueError("Head BLAS thread budget differs from the requested configuration")
    if not names or len(set(names)) != len(names) or any(n not in METHODS for n in names):
        raise ValueError("Invalid methods")
    load_start = time.perf_counter()
    prepared = Prepared(directory, config, allow_test_fixture=allow_test_fixture)
    shared_load_s = time.perf_counter() - load_start
    methods = {}
    # Vary initialization order by seed, independent of data/optimizer RNGs.
    shift = prepared.seed % len(names)
    for name in names[shift:] + names[:shift]:
        methods[name] = Method(name, prepared, config)
    if len({heads_digest(m.heads) for m in methods.values()}) != 1:
        raise AssertionError("Methods did not start from identical heads")
    initial_digest = heads_digest(next(iter(methods.values())).heads)
    records, metrics = [], []
    audit_s, evaluation_s, relation_checks, membership_checks = 0.0, 0.0, 0, 0
    for round_number in range(1, config.rounds + 1):
        outputs, rows = {}, {}
        shift = (prepared.seed + round_number) % len(names)
        for name in names[shift:] + names[:shift]:
            record, relations, snapshots = methods[name].step(round_number)
            records.append(record)
            rows[name], outputs[name] = record, (relations, snapshots)
        if validate:
            stage = time.perf_counter()
            collaborators = [name for name in names if name != "Local"]
            if len({rows[n]["head_digest_after_public"] for n in collaborators}) > 1:
                raise AssertionError("B/E/D real training trajectories diverged")
            if collaborators and any(rows[n]["traffic"] != rows[collaborators[0]]["traffic"] for n in collaborators):
                raise AssertionError("B/E/D communication traces differ")
            for name in collaborators:
                relation, member = audit(methods[name], *outputs[name], prepared)
                relation_checks += relation
                membership_checks += member
            audit_s += time.perf_counter() - stage
        if round_number % config.eval_every == 0 or round_number == config.rounds:
            stage = time.perf_counter()
            for name in names:
                metrics.append({"method": name, "round": round_number,
                                **evaluate(methods[name].heads, prepared, config)})
            evaluation_s += time.perf_counter() - stage
        if progress and (round_number % 10 == 0 or round_number == config.rounds):
            print(f"real IID seed={prepared.seed}: {round_number}/{config.rounds}", flush=True)
    summary = {}
    common_cost = prepared.metadata["preparation_wall_seconds_excluding_download"] + shared_load_s
    for name in names:
        method = methods[name]
        rows = [r for r in records if r["method"] == name]
        pipeline = method.initialization_seconds + sum(r["pipeline_seconds"] for r in rows)
        latest = next(m for m in reversed(metrics) if m["method"] == name)
        summary[name] = {
            "initialization_seconds": method.initialization_seconds,
            "training_pipeline_seconds": pipeline,
            "with_shared_preparation_seconds": common_cost + pipeline,
            **{phase + "_seconds": sum(r[phase + "_seconds"] for r in rows)
               for phase in ("private", "generation", "exchange", "public")},
            "teacher_recompute_fraction_after_bootstrap": None if name == "Local" or config.rounds == 1 else
                sum(r["teacher_forward_endpoints"] for r in rows[1:])
                / (config.samples * len(config.dimensions) * (config.rounds - 1)),
            "student_forward_endpoints": sum(r["student_forward_endpoints"] for r in rows),
            "private_optimizer_steps": sum(r['private_optimizer_steps'] for r in rows),
            "public_optimizer_steps": sum(r['public_optimizer_steps'] for r in rows),
            "candidate_size_after_bootstrap": None if config.rounds == 1 else
                sum(s['candidate_entries'] for r in rows[1:] for s in r['client_statistics'])
                / (config.samples * len(config.dimensions) * (config.rounds - 1)),
            "certified_edge_fraction_after_bootstrap": None if config.rounds == 1 else
                sum(r['certified_edges_before_refresh'] for r in rows[1:])
                / (len(prepared.edges) * len(config.dimensions) * (config.rounds - 1)),
            "traffic": {} if method.protocol is None else method.protocol.traffic.snapshot(),
            "persistent_method_array_bytes": method.persistent_bytes(), "final_metrics": latest,
        }
    result = {"dataset": prepared.metadata["dataset"], "seed": prepared.seed, "config": config.json(),
            "case_id": config.case_id, "edge_count": len(prepared.edges),
            "graph_sha256": hashlib.sha256(prepared.edges.tobytes()).hexdigest(),
            "initial_head_digest": initial_digest,
            "shared_private_evidence": {name: checksum for name, checksum in prepared.metadata['files'].items()
                                        if any(key in name for key in ('private', 'pseudo', 'autoencoder'))},
            "prepared_directory": str(prepared.directory.resolve()),
            "common_preparation_seconds": prepared.metadata["preparation_wall_seconds_excluding_download"],
            "shared_feature_loading_seconds": shared_load_s,
            "head_threadpools": pools,
            "common_cost_policy": "C0 prepares the SAME private data and ENTIRE maximum public pool once per seed, including test features. C0+loading+T is accounting under this shared maximum-pool policy, NOT each smaller M's minimum standalone preparation cost, NOT divided by method/case count. Cached reuse does not repay C0.",
            "validation": {"enabled": validate, "mismatches": 0 if validate else None,
                           "relation_comparisons": relation_checks,
                           "candidate_membership_comparisons": membership_checks,
                           "audit_seconds_excluded": audit_s, "evaluation_seconds_excluded": evaluation_s},
            "scope": "Real private CE and public BCE SGD on private-pretrained frozen MLP features; CPU float64 heads; serial clients; in-memory application messages, no real network/election/failover",
            "summary": summary, "round_records": records, "metrics": metrics}
    prepared.close()
    return result
