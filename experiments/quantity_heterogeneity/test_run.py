"""Focused regression tests for the frozen quantity-heterogeneity design."""
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from threadpoolctl import threadpool_limits

from experiments.client_scaling.engine import run as legacy_engine_run
from experiments.lr_client_scaling.design import plan as p3_plan
from experiments.private_workload.design import Spec
from experiments.quantity_heterogeneity import data, engine
from experiments.quantity_heterogeneity.design import (
    METHODS, PARTITIONS, PROFILES, capacities, filename, plan, schedule,
)
from experiments.quantity_heterogeneity.partition import partition_indices
from experiments.stl10_compute.run import TRAJECTORY_KEYS


def _tempdir():
    return tempfile.TemporaryDirectory(prefix="quantity-test-", dir=Path(__file__).parent)


def _spec(profile="strong", preset="smoke", rounds=2):
    spec = plan(preset)[profile]
    return Spec(replace(spec.config, rounds=rounds, eval_every=2), spec.policy,
                spec.steps, spec.private_limit)


def _assert_raises(exception):
    return unittest.TestCase().assertRaises(exception)


def _run_engine(directory, spec, method, **kwargs):
    with threadpool_limits(limits=spec.config.threads):
        return engine.run(directory, spec, method, **kwargs)


def test_design_profiles_schedule_and_full_equal_anchor():
    assert capacities("full", "equal") == (400,) * 6
    assert capacities("full", "moderate") == (200, 400, 600, 200, 400, 600)
    assert capacities("full", "strong") == (100, 400, 700, 100, 400, 700)
    assert capacities("smoke", "equal") == (32,) * 6
    assert capacities("smoke", "moderate") == (16, 32, 48, 16, 32, 48)
    assert capacities("smoke", "strong") == (10, 32, 54, 10, 32, 54)
    assert plan("full")["equal"].json() == p3_plan("full", "fixed_per_client")[1].json()
    for preset, expected in (("full", 54), ("smoke", 18)):
        jobs = schedule(preset)
        assert len(jobs) == expected
        assert {j["profile"] for j in jobs} == set(PROFILES)
        assert all(j["regime"] == "quantity_" + j["profile"] for j in jobs)
        assert all({j["method"] for j in jobs if (j["seed"], j["partition"], j["profile"]) == key} == set(METHODS)
                   for key in {(j["seed"], j["partition"], j["profile"]) for j in jobs})
    assert len(schedule("full", memory=True)) == 6
    assert len(schedule("smoke", memory=True)) == 6
    assert len({filename(j) for j in schedule("full")}) == 54


def test_capacity_partitions_are_deterministic_complete_and_class_balanced():
    labels = np.tile(np.arange(10, dtype=np.int64), 250)  # 2,500 labeled IDs
    for profile in PROFILES:
        caps = capacities("full", profile)
        for partition in PARTITIONS:
            for seed in (1001, 1002, 1003):
                pub, clients, diag = partition_indices(labels, 100, 6, seed, partition, caps)
                pub2, clients2, diag2 = partition_indices(labels, 100, 6, seed, partition, caps)
                assert np.array_equal(pub, pub2)
                assert all(np.array_equal(a, b) for a, b in zip(clients, clients2))
                assert diag == diag2
                assert [len(a) for a in clients] == list(caps)
                joined = np.concatenate([pub, *clients])
                assert len(joined) == len(labels) and len(np.unique(joined)) == len(labels)
                assert np.array_equal(np.sort(joined), np.arange(len(labels)))
                hist = np.sum([np.bincount(labels[x], minlength=10) for x in clients], axis=0)
                expected_totals = np.bincount(labels[np.setdiff1d(np.arange(len(labels)), pub)], minlength=10)
                assert np.array_equal(hist, expected_totals)
                assert diag["private_count"] == 2400
    labels = np.tile(np.arange(10, dtype=np.int64), 25)
    for bad in ((10, 10), (10, 10, 10, 10, 10, 39), (9, 11, 10, 10, 10, 39)):
        with _assert_raises(ValueError):
            partition_indices(labels, 10, 6, 1001, "iid", bad)


def test_equal_partition_matches_legacy_exactly_for_both_modes_and_seeds():
    from experiments.noniid_clustering.data import partition_indices as legacy

    labels = np.tile(np.arange(10, dtype=np.int64), 250)
    for partition in PARTITIONS:
        for seed in (1001, 1002, 1003):
            actual = partition_indices(labels, 100, 6, seed, partition,
                                       capacities("full", "equal"))
            expected = legacy(labels, 100, 6, seed, partition)
            assert np.array_equal(actual[0], expected[0])
            assert all(np.array_equal(a, b) for a, b in zip(actual[1], expected[1]))
            assert actual[2] == expected[2]


def test_fixture_cache_verification_rejects_tamper_and_wrong_profile_then_restores():
    with _tempdir() as tmp:
        root = Path(tmp)
        cache, source = root / "cache", root / "source"
        spec = _spec("strong", rounds=2)
        prepared = data.prepare(cache, source, spec, 1001, "iid", profile="strong", fixture=True)
        assert data.verify(prepared, spec, 1001, "iid", profile="strong", fixture=True)
        marker = prepared / "prepared.json"
        original_marker = marker.read_bytes()
        meta = json.loads(original_marker)
        meta["profile"] = "moderate"
        marker.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        with _assert_raises(ValueError):
            data.verify(prepared, spec, 1001, "iid", profile="strong", fixture=True)
        marker.write_bytes(original_marker)

        target = prepared / "client_0_pseudo.npy"
        original_array = target.read_bytes()
        damaged = bytearray(original_array)
        damaged[-1] ^= 1
        target.write_bytes(damaged)
        with _assert_raises(ValueError):
            data.verify(prepared, spec, 1001, "iid", profile="strong", fixture=True)
        target.write_bytes(original_array)
        assert data.verify(prepared, spec, 1001, "iid", profile="strong", fixture=True)


def test_fixture_engine_matches_legacy_equal_and_checks_strong_bed_and_memory():
    with _tempdir() as tmp:
        root = Path(tmp)
        source = root / "source"
        equal_spec = _spec("equal", rounds=2)
        from experiments.stl10_transfer.data import prepare as legacy_prepare
        equal_dir = legacy_prepare(root / "equal-cache", source, equal_spec.config, 1001,
                                  "iid", fixture=True)
        for method in METHODS:
            current = _run_engine(equal_dir, equal_spec, method, profile="equal", fixture=True)
            with threadpool_limits(limits=equal_spec.config.threads):
                legacy = legacy_engine_run(equal_dir, equal_spec, method, fixture=True)
            assert current["initial_head_digest"] == legacy["initial_head_digest"]
            assert current["graph_sha256"] == legacy["graph_sha256"]
            for left, right in zip(current["round_records"], legacy["round_records"]):
                assert {k: left[k] for k in TRAJECTORY_KEYS} == {k: right[k] for k in TRAJECTORY_KEYS}
            assert [{k: v for k, v in row.items() if k != "method"} for row in current["metrics"]] == [
                {k: v for k, v in row.items() if k != "method"} for row in legacy["metrics"]]

        strong_spec = _spec("strong", rounds=2)
        strong_dir = data.prepare(root / "strong-cache", source, strong_spec, 1001, "iid",
                                  profile="strong", fixture=True)
        paired = {m: _run_engine(strong_dir, strong_spec, m, profile="strong", fixture=True)
                  for m in METHODS}
        for method in ("E", "D"):
            assert paired[method]["initial_head_digest"] == paired["B"]["initial_head_digest"]
            assert paired[method]["graph_sha256"] == paired["B"]["graph_sha256"]
            for left, right in zip(paired[method]["round_records"], paired["B"]["round_records"]):
                assert {k: left[k] for k in TRAJECTORY_KEYS} == {k: right[k] for k in TRAJECTORY_KEYS}
            assert [{k: v for k, v in row.items() if k != "method"} for row in paired[method]["metrics"]] == [
                {k: v for k, v in row.items() if k != "method"} for row in paired["B"]["metrics"]]
        memory_d = _run_engine(strong_dir, strong_spec, "D", profile="strong", fixture=True, memory=True)
        assert memory_d["metrics"] == [] and memory_d["coverage_records"] == []
        assert memory_d["validation"]["enabled"] is False


def test_runner_record_and_group_verifiers_accept_quantity_capacities():
    from experiments.quantity_heterogeneity.run import non_time_rows, verify_groups, verify_record
    from experiments.stl10_transfer.run import seal

    with _tempdir() as tmp:
        root = Path(tmp)
        spec = _spec("strong", rounds=2)
        prepared = data.prepare(root / "cache", root / "source", spec, 1001, "iid",
                                profile="strong", fixture=True)
        records = []
        meta0 = dict(seed=1001, partition="iid", profile="strong", regime="quantity_strong", clients=6,
                     case_id=spec.case_id, method="B", block=0, position=0)
        base = _run_engine(prepared, spec, "B", profile="strong", fixture=True)
        identity = ("seed", "partition", "profile", "regime", "clients", "method")
        run_meta = {**base, **{k: meta0[k] for k in identity},
                    "memory_mode": False, "process_peak_bytes": 0,
                    "worker_started_utc": 0.0, "worker_ended_utc": 0.0,
                    "worker_started_power": {"ac_line_status": 1}, "worker_ended_power": {"ac_line_status": 1}}
        record = seal(run_meta)
        verify_record(record, meta0, spec, prepared, False, True)
        assert [m["round"] for m in record["metrics"]] == [2]
        assert all(not any(k.endswith("_seconds") for k in row) for row in non_time_rows(record))
        broken = dict(record)
        broken["round_records"] = [dict(r) for r in record["round_records"]]
        broken["round_records"][0]["private_samples_per_client"] = list(broken["round_records"][0]["private_samples_per_client"])
        broken["round_records"][0]["private_samples_per_client"][0] += 1
        broken = seal({k: v for k, v in broken.items() if k != "run_sha256"})
        with _assert_raises(ValueError):
            verify_record(broken, meta0, spec, prepared, False, True)
        records.append((meta0, record))
        for method in ("E", "D"):
            method_meta = {**meta0, "method": method}
            current = _run_engine(prepared, spec, method, profile="strong", fixture=True)
            current.update({k: method_meta[k] for k in identity})
            current.update(memory_mode=False, process_peak_bytes=0, worker_started_utc=0.0,
                           worker_ended_utc=0.0, worker_started_power={"ac_line_status": 1},
                           worker_ended_power={"ac_line_status": 1})
            signed = seal(current)
            verify_record(signed, method_meta, spec, prepared, False, True)
            records.append((method_meta, signed))
        assert len(verify_groups(records)) == 1


def load_tests(loader, standard_tests, pattern):
    functions = [value for name, value in sorted(globals().items())
                 if name.startswith("test_") and callable(value)]
    return unittest.TestSuite(unittest.FunctionTestCase(function) for function in functions)


if __name__ == "__main__":
    unittest.main()
