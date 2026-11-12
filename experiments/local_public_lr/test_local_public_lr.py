"""Regression tests for per-client public-LR intervention and probes."""
from pathlib import Path
import csv
import json
import tempfile
import unittest
from unittest import mock

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.local_public_lr import design, engine, report
from experiments.local_public_lr.run import verify_record
from experiments.quantity_heterogeneity import data as quantity_data
from experiments.quantity_heterogeneity.engine import run as quantity_engine_run
from experiments.public_budget.student import selected_edges
from experiments.public_scaling.head import relation_loss_grad
from experiments.stl10_compute.run import TRAJECTORY_KEYS
from experiments.stl10_transfer.run import seal


def _same_rng_state(left, right):
    return left[0] == right[0] and np.array_equal(left[1], right[1]) and left[2:] == right[2:]


def _without_times(row):
    return {key: value for key, value in row.items() if not key.endswith("_seconds")}


def _run(directory, spec, branch, **kwargs):
    with threadpool_limits(limits=spec.config.threads):
        return engine.run(directory, spec, branch=branch, fixture=True,
                          progress=False, **kwargs)


class _ReferenceHead:
    def __init__(self, head):
        self.w = head.w.copy()
        self.b = head.b.copy()

    def apply(self, dw, db, rate):
        self.w -= rate * dw
        self.b -= rate * db


def test_design_freezes_exact_local_lr_vector_and_case_matrix():
    assert design.public_client_weights("baseline") == [.5] * 6
    assert design.public_client_weights("local_lr") == [.125, .5, .5, .125, .5, .5]
    for preset, rounds, evaluation in (("full", 200, 20), ("smoke", 3, 1)):
        specs = design.plan(preset)
        assert set(specs) == {"baseline", "local_lr"}
        assert all(s.config.rounds == rounds and s.config.eval_every == evaluation for s in specs.values())
        assert all(s.config.public_weight == .5 for s in specs.values())
        cases = design.cases(preset)
        assert len(cases) == 1
        assert cases[0]["profile"] == "strong" and cases[0]["partition"] == "iid"
        assert cases[0]["seed"] == 1001 and cases[0]["method"] == "B" and cases[0]["clients"] == 6
        assert len(design.schedule(preset)) == 2
    with unittest.TestCase().assertRaises(ValueError):
        design.public_client_weights("local_lr", clients=4)


def test_recovery_fails_if_any_checkpoint_or_client_is_missing():
    def make_record():
        return {"metrics": [dict(round=rnd, clients=[dict(client=c,
            occupied_clusters=2, largest_cluster_fraction=.98, nmi=.2)
            for c in range(6)]) for rnd in (160, 180, 200)]}

    assert report.recovery(make_record())["passed"] is True
    missing_round = make_record()
    missing_round["metrics"] = [m for m in missing_round["metrics"] if m["round"] != 180]
    assert report.recovery(missing_round)["passed"] is False
    missing_client = make_record()
    missing_client["metrics"][1]["clients"] = [c for c in missing_client["metrics"][1]["clients"]
                                               if c["client"] != 3]
    assert report.recovery(missing_client)["passed"] is False


def test_fixture_baseline_matches_quantity_engine_and_probes_do_not_change_training():
    with tempfile.TemporaryDirectory(prefix="local-public-lr-", dir=Path(__file__).parent) as tmp:
        root = Path(tmp)
        baseline_spec = design.plan("smoke")["baseline"]
        prepared = quantity_data.prepare(root / "cache", root / "source", baseline_spec,
            1001, "iid", profile="strong", fixture=True)
        rng_before = np.random.get_state()
        baseline = _run(prepared, baseline_spec, "baseline", enable_probes=True)
        rng_after = np.random.get_state()
        assert _same_rng_state(rng_before, rng_after)
        without_probes = _run(prepared, baseline_spec, "baseline", enable_probes=False)
        with threadpool_limits(limits=baseline_spec.config.threads):
            reference = quantity_engine_run(prepared, baseline_spec, "B", profile="strong", fixture=True)

        for candidate in (without_probes, reference):
            assert candidate["graph_sha256"] == baseline["graph_sha256"]
            assert candidate["initial_head_digest"] == baseline["initial_head_digest"]
            assert candidate["summary"]["B"]["final_head_digest"] == baseline["summary"]["B"]["final_head_digest"]
            assert [_without_times(row) for row in candidate["round_records"]] == [
                _without_times(row) for row in baseline["round_records"]]
            assert candidate["metrics"] == baseline["metrics"]
        assert without_probes["diagnostic_records"] == []
        assert len(baseline["diagnostic_records"]) == baseline_spec.config.rounds
        assert all({key for key in TRAJECTORY_KEYS} <= set(row)
                   for row in baseline["round_records"])

        # Exercise report exports with both historical intervention branches.
        history = {}
        for branch, weights in (("private_only", [.5] * 6),
                                ("low_lr", [.125, .5, .5, .125, .5, .5])):
            clone = dict(baseline)
            clone["branch"] = branch
            clone["public_client_weights"] = weights
            history[branch] = clone
        meta = dict(case_id=baseline["case_id"], seed=1001, partition="iid",
                    profile="strong", method="B", branch="baseline")
        report_dir = root / "report"
        report_dir.mkdir()
        report.reports(report_dir, [(meta, baseline)], {baseline["case_id"]: reference},
                       fixture=True, history=history)
        late_branches = {row["branch"] for row in csv.DictReader(
            (report_dir / "late_comparison.csv").open(encoding="utf-8"))}
        historical_branches = {row["branch"] for row in csv.DictReader(
            (report_dir / "historical_diagnostic_checkpoints.csv").open(encoding="utf-8"))}
        report_summary = json.loads((report_dir / "summary.json").read_text(encoding="utf-8"))
        rate_rows = list(csv.DictReader((report_dir / "client_rates.csv").open(encoding="utf-8")))
        assert {"private_only", "low_lr"} <= late_branches
        assert historical_branches == {"private_only", "low_lr"}
        assert set(report_summary["historical_reference_recovery"]) == {"private_only", "low_lr"}
        private_rates = [row for row in rate_rows if row["branch"] == "private_only"]
        assert len(private_rates) == 6
        assert all(row["public_update_active"] == "False" and row["effective_public_lr"] == "0.0"
                   for row in private_rates)


def test_local_lr_steps_match_independent_per_client_updates_and_tampering_is_rejected():
    with tempfile.TemporaryDirectory(prefix="local-public-lr-verify-", dir=Path(__file__).parent) as tmp:
        root = Path(tmp)
        spec = design.plan("smoke")["local_lr"]
        prepared = quantity_data.prepare(root / "cache", root / "source", spec,
            1001, "iid", profile="strong", fixture=True)
        baseline_spec = design.plan("smoke")["baseline"]
        baseline = _run(prepared, baseline_spec, "baseline")
        original_update = engine.update
        observed = []

        def step_and_check_reference(*args, **kwargs):
            actual_head, features, edges, targets, client_spec, seed, client, rnd = args
            expected_weight = .125 if client in (0, 3) else .5
            assert client_spec.config.public_weight == expected_weight
            reference_head = _ReferenceHead(actual_head)
            cfg = client_spec.config
            order = selected_edges(client_spec, seed, client, rnd)
            loss_sum = 0.0
            edge_count = endpoints = 0
            for offset in range(0, len(order), cfg.public_edge_batch):
                ids = order[offset:offset + cfg.public_edge_batch]
                vertices, inverse = np.unique(edges[ids].ravel(), return_inverse=True)
                loss, dw, db = relation_loss_grad(features[vertices], inverse.reshape(-1, 2),
                                                  targets[ids], reference_head.w, reference_head.b)
                reference_head.apply(dw, db, cfg.head_lr * expected_weight)
                loss_sum += loss * len(ids)
                edge_count += len(ids)
                endpoints += len(vertices)
            actual_result = original_update(*args, **kwargs)
            reference_result = (loss_sum / edge_count, endpoints, order)
            assert actual_result[:2] == reference_result[:2]
            assert np.array_equal(actual_result[2], reference_result[2])
            assert np.array_equal(actual_head.w, reference_head.w)
            assert np.array_equal(actual_head.b, reference_head.b)
            observed.append((client, client_spec.config.public_weight))
            return actual_result

        with mock.patch.object(engine, "update", side_effect=step_and_check_reference):
            result = _run(prepared, spec, "local_lr")
        assert baseline["initial_head_digest"] == result["initial_head_digest"]
        assert baseline["graph_sha256"] == result["graph_sha256"]
        base_clients = baseline["diagnostic_records"][0]["clients"]
        local_clients = result["diagnostic_records"][0]["clients"]
        for client in range(6):
            assert base_clients[client]["T0"] == local_clients[client]["T0"]
            assert base_clients[client]["T1"] == local_clients[client]["T1"]
            if client in (0, 3):
                assert base_clients[client]["T2"]["head_digest"] != local_clients[client]["T2"]["head_digest"]
            else:
                assert base_clients[client]["T2"]["head_digest"] == local_clients[client]["T2"]["head_digest"]
        for base_round, local_round in zip(baseline["diagnostic_records"], result["diagnostic_records"]):
            for base_client, local_client in zip(base_round["clients"], local_round["clients"]):
                assert base_client["private_order_sha256"] == local_client["private_order_sha256"]
                assert base_client["public_order_sha256"] == local_client["public_order_sha256"]
        assert len(observed) == spec.config.rounds * 6
        assert result["public_client_weights"] == [.125, .5, .5, .125, .5, .5]
        expected_effective = [spec.config.head_lr * weight for weight in result["public_client_weights"]]
        for diagnostic in result["diagnostic_records"]:
            assert [client["actual_public_effective_lr"] for client in diagnostic["clients"]] == expected_effective
        meta = dict(seed=1001, partition="iid", profile="strong", method="B", branch="local_lr")
        entry = dict(path=str(prepared.resolve()), probe_manifest=result["probe_manifest"])
        sealed = seal(dict(result))
        verify_record(sealed, meta, spec, entry, True)

        wrong_vector = dict(sealed)
        wrong_vector["public_client_weights"] = [.5] * 6
        wrong_vector = seal(wrong_vector)
        with unittest.TestCase().assertRaises(ValueError):
            verify_record(wrong_vector, meta, spec, entry, True)

        wrong_rate = dict(sealed)
        wrong_rate["diagnostic_records"] = [dict(row, clients=[dict(c) for c in row["clients"]])
                                            for row in sealed["diagnostic_records"]]
        wrong_rate["diagnostic_records"][0]["clients"][0]["actual_public_effective_lr"] += .01
        wrong_rate = seal(wrong_rate)
        with unittest.TestCase().assertRaises(ValueError):
            verify_record(wrong_rate, meta, spec, entry, True)


def load_tests(loader, standard_tests, pattern):
    functions = [value for name, value in sorted(globals().items())
                 if name.startswith("test_") and callable(value)]
    return unittest.TestSuite(unittest.FunctionTestCase(function) for function in functions)


if __name__ == "__main__":
    unittest.main()
