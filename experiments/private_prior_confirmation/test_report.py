import csv
import copy
import json

import pytest

from experiments.private_prior_confirmation.report import report


def _run(seed, partition, method, repeat, seconds):
    case = {"seed": seed, "partition": partition,
            "case_id": f"strong_{partition}_seed{seed}",
            "method": method, "repeat": repeat}
    clients = [{"client": i, "acc": .5, "nmi": .4, "ari": .3,
                "occupied_clusters": 2, "largest_cluster_fraction": .7}
               for i in range(6)]
    rounds = [{"round": rnd, "teacher_positive_fractions": [.2] * 6}
              for rnd in range(1, 201)]
    metrics = [{"round": rnd, "clients": clients} for rnd in (160, 180, 200)]
    record = {"summary": {method: {
        "head_pipeline_seconds": seconds,
        "measured_stage_seconds": seconds + 1,
        "generation_seconds": seconds / 10,
        "with_shared_preparation_seconds": seconds + 100,
        "final_metrics": {"clients": clients, "mean": {"acc": .5}},
    }}, "round_records": rounds, "metrics": metrics,
        "common_preparation_seconds": 80, "shared_loading_seconds": 20}
    return case, record


def test_repeat_mean_then_seed_pairing_drives_performance_decisions(tmp_path):
    records = []
    # One seed has a slow B repeat and fast D repeats; the paired ratio must
    # use method means, then the median of the three seed-level ratios.
    for seed, b_values, d_values in (
        (1201, (10, 20, 30), (8, 8, 8)),
        (1202, (10, 10, 10), (8, 8, 8)),
        (1203, (10, 10, 10), (8, 8, 8)),
    ):
        for repeat, (b, d) in enumerate(zip(b_values, d_values)):
            records += [_run(seed, "iid", "B", repeat, b),
                        _run(seed, "iid", "D", repeat, d),
                        _run(seed, "iid", "E", repeat, 10)]
    payload = report(tmp_path, records)
    iid = payload["partitions"]["iid"]
    assert iid["paired_ratios_D_over_B_by_seed"]["1201"] == .4
    assert iid["D_over_B_median"] == .8
    assert iid["C1"]["pass"]
    assert iid["C2"]["pass"]
    assert iid["C3"]["pass"]
    assert iid["quality"]["pass"]
    assert iid["overall_pass"]
    with (tmp_path / "raw_runs.csv").open(encoding="utf-8-sig", newline="") as f:
        raw = list(csv.DictReader(f))
    assert len(raw) == 27
    assert raw[0]["shared_preparation_seconds"] == "80"
    assert raw[0]["head_pipeline_seconds"] == "10"
    assert json.loads((tmp_path / "decision.json").read_text(encoding="utf-8"))["partitions"]["iid"]["overall_pass"]


def test_smoke_and_failed_quality_guards_are_exploratory(tmp_path):
    records = [_run(1201, "iid", method, repeat, seconds)
               for method, seconds in (("B", 10), ("E", 10), ("D", 5))
               for repeat in range(3)]
    # Corrupt one client at a required quality checkpoint.
    rec = records[0][1]
    rec["metrics"][1]["clients"][2]["occupied_clusters"] = 1
    payload = report(tmp_path, records, smoke=True)
    iid = payload["partitions"]["iid"]
    assert iid["C1"]["pass"] is False
    assert iid["quality"]["pass"] is False
    assert iid["overall_pass"] is False
    assert payload["mode"] == "exploratory_smoke"
    rows = list(csv.DictReader((tmp_path / "quality.csv").open(encoding="utf-8-sig", newline="")))
    assert any(row["client"] == "2" and row["round"] == "180" for row in rows)


@pytest.mark.parametrize("gap", ("checkpoint", "client", "teacher_round"))
def test_quality_requires_complete_checkpoints_clients_and_last_40_rounds(tmp_path, gap):
    records = [_run(seed, "iid", method, repeat, seconds)
               for seed in (1201, 1202, 1203)
               for method, seconds in (("B", 10), ("E", 10), ("D", 5))
               for repeat in range(3)]
    target = next(record for case, record in records
                  if case["seed"] == 1201 and case["method"] == "B" and case["repeat"] == 0)
    target = copy.deepcopy(target)
    for index, (case, _) in enumerate(records):
        if case["seed"] == 1201 and case["method"] == "B" and case["repeat"] == 0:
            records[index] = (case, target)
            break
    if gap == "checkpoint":
        target["metrics"] = [m for m in target["metrics"] if m["round"] != 180]
    elif gap == "client":
        target["metrics"][0]["clients"] = target["metrics"][0]["clients"][:-1]
    else:
        target["round_records"] = [r for r in target["round_records"] if r["round"] != 180]

    result = report(tmp_path / gap, records)
    quality = result["partitions"]["iid"]["quality"]
    if gap in ("checkpoint", "client"):
        assert quality["cluster_guard_by_seed"]["1201"] is False
    else:
        assert quality["teacher_C0_C3_le_0.40_by_seed"]["1201"] is False
    assert quality["pass"] is False
