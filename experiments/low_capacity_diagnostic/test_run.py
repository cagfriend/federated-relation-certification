"""Focused tests for the low-capacity stability diagnostic."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.low_capacity_diagnostic import design, engine, probes, report
from experiments.quantity_heterogeneity import data as quantity_data
from experiments.quantity_heterogeneity.engine import run as old_quantity_run
from experiments.stl10_compute.run import TRAJECTORY_KEYS


def _state_equal(left, right):
    return (left[0] == right[0] and np.array_equal(left[1], right[1])
            and left[2:] == right[2:])


def _without_times(row):
    return {key: value for key, value in row.items() if not key.endswith("_seconds")}


def _thread_limited_run(directory, spec, branch, **kwargs):
    with threadpool_limits(limits=spec.config.threads):
        return engine.run(directory, spec, branch=branch, fixture=True,
                          progress=False, **kwargs)


def test_plan_pins_branch_rounds_and_public_dose():
    for preset, baseline_rounds, diagnostic_rounds, evaluation in (
            ("full", 40, 200, 20), ("smoke", 2, 3, 1)):
        specs = design.plan(preset)
        assert set(specs) == {"baseline", "private_only", "low_lr"}
        assert specs["baseline"].config.rounds == baseline_rounds
        assert specs["private_only"].config.rounds == diagnostic_rounds
        assert specs["low_lr"].config.rounds == diagnostic_rounds
        assert all(spec.config.eval_every == evaluation for spec in specs.values())
        assert specs["baseline"].config.public_weight == .5
        assert specs["private_only"].config.public_weight == .5
        assert specs["low_lr"].config.public_weight == .125
        assert len(design.cases(preset)) == (4 if preset == "full" else 2)
        assert len(design.schedule(preset)) == (12 if preset == "full" else 6)
    with unittest.TestCase().assertRaises(ValueError):
        design.plan("unknown")


def test_recovery_requires_every_client_at_every_checkpoint_and_strict_threshold():
    def record():
        return {"metrics": [dict(round=rnd, clients=[dict(client=c,
            occupied_clusters=2, largest_cluster_fraction=.98, nmi=.2)
            for c in range(6)]) for rnd in (160, 180, 200)]}

    passing = report.recovery(record())
    assert passing["passed"] is True
    assert all(passing["client_results"].values())

    missing_round = record()
    missing_round["metrics"] = [m for m in missing_round["metrics"] if m["round"] != 180]
    assert report.recovery(missing_round)["passed"] is False

    missing_client = record()
    missing_client["metrics"][1]["clients"] = [c for c in missing_client["metrics"][1]["clients"]
                                               if c["client"] != 3]
    assert report.recovery(missing_client)["passed"] is False

    threshold = record()
    threshold["metrics"][2]["clients"][0]["largest_cluster_fraction"] = .99
    assert report.recovery(threshold)["passed"] is False


def test_probe_selection_and_manifest_are_repeatable_without_global_rng_changes():
    np.random.seed(20261111)
    before = np.random.get_state()
    one = probes.selection(1001, 128, 32)
    two = probes.selection(1001, 128, 32)
    manifest = probes.manifest(1001, np.arange(1000, 1128, dtype=np.int64), 32)
    after = np.random.get_state()
    assert np.array_equal(one, two)
    assert np.all(np.diff(one) > 0)
    assert manifest["local_indices"] == one.tolist()
    assert manifest["public_ids"] == (one + 1000).tolist()
    assert _state_equal(before, after)


def test_fixture_branches_are_read_only_and_match_the_frozen_baseline():
    # Keep all temporary fixture/cache files within the package and auto-clean them.
    with tempfile.TemporaryDirectory(prefix="low-capacity-test-",
                                    dir=Path(__file__).parent) as temporary:
        root = Path(temporary)
        baseline_spec, private_spec, low_lr_spec = (
            design.plan("smoke")[name] for name in ("baseline", "private_only", "low_lr"))
        prepared = quantity_data.prepare(root / "cache", root / "source", baseline_spec,
            1001, "iid", profile="strong", fixture=True)

        rng_before = np.random.get_state()
        baseline = _thread_limited_run(prepared, baseline_spec, "baseline", enable_probes=True)
        rng_after = np.random.get_state()
        assert _state_equal(rng_before, rng_after), "diagnostic probes changed NumPy global RNG state"

        unprobed = _thread_limited_run(prepared, baseline_spec, "baseline", enable_probes=False)
        with threadpool_limits(limits=baseline_spec.config.threads):
            old = old_quantity_run(prepared, baseline_spec, "B", profile="strong", fixture=True)
        for candidate in (unprobed, old):
            assert candidate["graph_sha256"] == baseline["graph_sha256"]
            assert candidate["initial_head_digest"] == baseline["initial_head_digest"]
            assert candidate["summary"]["B"]["final_head_digest"] == baseline["summary"]["B"]["final_head_digest"]
            assert [_without_times(row) for row in candidate["round_records"]] == [
                _without_times(row) for row in baseline["round_records"]]
            assert candidate["metrics"] == baseline["metrics"]
        assert unprobed["diagnostic_records"] == []
        assert len(baseline["diagnostic_records"]) == baseline_spec.config.rounds
        for round_record in baseline["diagnostic_records"]:
            for client in round_record["clients"]:
                assert {"private", "public", "head_digest"} <= set(client["T0"])
                assert {"private", "public", "private_update_delta"} <= set(client["T1"])
                assert {"private", "public", "public_update_delta"} <= set(client["T2"])
                assert "private_update_loss" in client and "positive_relation_fraction_T1" in client
                assert client["public_update_loss"] is not None

        # Private-only must still perform private SGD, while making no public update.
        with mock.patch.object(engine, "update", side_effect=AssertionError("public update called")):
            private_only = _thread_limited_run(prepared, private_spec, "private_only")
        assert private_only["summary"]["B"]["public_optimizer_steps"] == 0
        assert private_only["summary"]["B"]["student_forward_endpoints"] == 0
        assert all(row["public_loss"] is None and row["private_optimizer_steps"] > 0
                   and row["private_forward_endpoints"] > 0
                   for row in private_only["round_records"])
        for round_record in private_only["diagnostic_records"]:
            for client in round_record["clients"]:
                assert client["T1"]["head_digest"] == client["T2"]["head_digest"]
                assert client["T2"]["public_update_delta"]["parameter_l2"] == 0.0
                assert client["public_update_loss"] is None

        original_update = engine.update
        observed_weights = []

        def capture_update(*args, **kwargs):
            observed_weights.append(args[4].config.public_weight)
            return original_update(*args, **kwargs)

        with mock.patch.object(engine, "update", side_effect=capture_update) as update_mock:
            low_lr = _thread_limited_run(prepared, low_lr_spec, "low_lr")
        assert update_mock.call_count > 0
        assert observed_weights and all(weight == .125 for weight in observed_weights)
        assert low_lr["config"]["public_weight"] == .125
        assert low_lr["summary"]["B"]["public_optimizer_steps"] > 0


def load_tests(loader, standard_tests, pattern):
    functions = [value for name, value in sorted(globals().items())
                 if name.startswith("test_") and callable(value)]
    return unittest.TestSuite(unittest.FunctionTestCase(function) for function in functions)


if __name__ == "__main__":
    unittest.main()
