"""Summarize validated private-prior confirmation records."""
import csv
import json
from pathlib import Path
import statistics


METHODS = ("B", "E", "D")
PARTITIONS = ("iid", "dirichlet_0.1")
CHECKPOINTS = (160, 180, 200)
CLIENT_NAMES = {0: "C0", 3: "C3"}


def _summary(record, method):
    return record["summary"][method]


def _metrics(summary):
    """Support the engine's {clients, mean} payload and older wrapped form."""
    value = summary.get("final_metrics") or {}
    if isinstance(value, dict) and "clients" in value:
        return value["clients"]
    if isinstance(value, list):
        return value
    return []


def _round_fraction(row):
    values = row.get("teacher_positive_fractions")
    if values is None:
        values = row.get("positive_relation_fractions")
    if values is None:
        return None
    return [float(x) for x in values]


def _write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _mean(xs):
    return statistics.fmean(xs) if xs else None


def _decision(records, smoke):
    # First average technical repeats for every (partition, seed, method),
    # then pair D against B/E by seed. The seed, not each run, is the unit.
    cells = {}
    for case, record in records:
        key = (case["partition"], int(case["seed"]), case["method"])
        cells.setdefault(key, []).append(record)
    partitions = {}
    for partition in sorted({key[0] for key in cells}):
        seeds = sorted({key[1] for key in cells if key[0] == partition})
        means = {}
        for seed in seeds:
            means[seed] = {}
            for method in METHODS:
                runs = cells[(partition, seed, method)]
                means[seed][method] = statistics.fmean(
                    float(_summary(r, method)["head_pipeline_seconds"]) for r in runs)
        db = {seed: means[seed]["D"] / means[seed]["B"] for seed in seeds}
        de = {seed: means[seed]["D"] / means[seed]["E"] for seed in seeds}
        win_db = sum(means[s]["D"] < means[s]["B"] for s in seeds)
        win_de = sum(means[s]["D"] < means[s]["E"] for s in seeds)
        formal = not smoke and len(seeds) == 3
        c1_value = statistics.median(db.values())
        c2_value = statistics.median(de.values())
        partitions[partition] = {
            "seed_method_mean_head_pipeline_seconds": {
                str(seed): means[seed] for seed in seeds},
            "paired_ratios_D_over_B_by_seed": {str(k): v for k, v in db.items()},
            "paired_ratios_D_over_E_by_seed": {str(k): v for k, v in de.items()},
            "D_over_B_median": c1_value,
            "D_over_B_min_max": [min(db.values()), max(db.values())],
            "D_over_E_median": c2_value,
            "D_over_E_min_max": [min(de.values()), max(de.values())],
            "D_wins_vs_B": {"count": win_db, "seeds": len(seeds)},
            "D_wins_vs_E": {"count": win_de, "seeds": len(seeds)},
            "C1": {"threshold": "median(D/B) <= 0.80", "value": c1_value,
                   "pass": formal and c1_value <= 0.80},
            "C2": {"threshold": "median(D/E) <= 0.95", "value": c2_value,
                   "pass": formal and c2_value <= 0.95},
            "C3": {"threshold": "at least 2/3 seed wins against each method",
                   "D_beats_B": formal and win_db >= 2,
                   "D_beats_E": formal and win_de >= 2,
                   "pass": formal and win_db >= 2 and win_de >= 2},
            "formal_performance_decision": formal,
        }
    return partitions


def report(out, records, smoke=False):
    """Write raw, paired, quality and decision artifacts for validated runs.

    `records` is an iterable of `(case, record)` pairs; case carries seed,
    partition, case_id, method and repeat. In smoke mode all decisions remain
    exploratory, regardless of whether a small sample happens to meet a gate.
    """
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    records = list(records)
    raw_rows = []
    for case, record in records:
        method = case["method"]
        summary = _summary(record, method)
        raw_rows.append({
            "case_id": case["case_id"], "seed": case["seed"],
            "partition": case["partition"], "method": method,
            "repeat": case["repeat"],
            "head_pipeline_seconds": summary.get("head_pipeline_seconds"),
            "measured_stage_seconds": summary.get("measured_stage_seconds"),
            "generation_seconds": summary.get("generation_seconds"),
            "with_shared_preparation_seconds": summary.get("with_shared_preparation_seconds"),
            "shared_preparation_seconds": record.get("common_preparation_seconds"),
            "shared_loading_seconds": record.get("shared_loading_seconds"),
        })
    _write_csv(out / "raw_runs.csv", raw_rows, [
        "case_id", "seed", "partition", "method", "repeat",
        "head_pipeline_seconds", "measured_stage_seconds", "generation_seconds",
        "with_shared_preparation_seconds", "shared_preparation_seconds", "shared_loading_seconds"])

    decisions = _decision(records, smoke)
    pair_rows = []
    for partition, detail in decisions.items():
        means = detail["seed_method_mean_head_pipeline_seconds"]
        for seed, values in means.items():
            pair_rows.append({"partition": partition, "seed": seed,
                              **{f"{m}_mean_head_pipeline_seconds": values[m] for m in METHODS},
                              "D_over_B": detail["paired_ratios_D_over_B_by_seed"][seed],
                              "D_over_E": detail["paired_ratios_D_over_E_by_seed"][seed],
                              "D_beats_B": values["D"] < values["B"],
                              "D_beats_E": values["D"] < values["E"]})
    _write_csv(out / "seed_pairs.csv", pair_rows, [
        "partition", "seed", "B_mean_head_pipeline_seconds", "E_mean_head_pipeline_seconds",
        "D_mean_head_pipeline_seconds", "D_over_B", "D_over_E", "D_beats_B", "D_beats_E"])

    # Quality is measured on B repeat 0 only, since the validated method
    # trajectories are identical across methods/repeats.
    quality_rows = []
    quality_ok = {}
    teacher_ok = {}
    for partition in sorted({case["partition"] for case, _ in records}):
        seeds = sorted({int(case["seed"]) for case, _ in records if case["partition"] == partition})
        quality_ok[partition] = {}
        teacher_ok[partition] = {}
        for seed in seeds:
            anchor = next((record for case, record in records
                           if case["partition"] == partition and int(case["seed"]) == seed
                           and case["method"] == "B" and int(case["repeat"]) == 0), None)
            if anchor is None:
                quality_ok[partition][str(seed)] = False
                teacher_ok[partition][str(seed)] = False
                continue
            metrics = _metrics(_summary(anchor, "B"))
            checkpoint_checks = []
            for checkpoint in CHECKPOINTS:
                matching = [m for m in (anchor.get("metrics") or [])
                            if int(m.get("round", -1)) == checkpoint]
                metric_at_round = matching[0] if len(matching) == 1 else None
                clients = metric_at_round.get("clients", []) if metric_at_round else []
                by_client = {int(item["client"]): item for item in clients
                             if item.get("client") is not None}
                complete = (len(clients) == 6 and len(by_client) == 6
                            and set(by_client) == set(range(6)))
                for item in clients:
                    quality_rows.append({"kind": "checkpoint", "partition": partition,
                        "seed": seed, "round": checkpoint, "client": item.get("client"),
                        "acc": item.get("acc"), "nmi": item.get("nmi"), "ari": item.get("ari"),
                        "occupied_clusters": item.get("occupied_clusters"),
                        "largest_cluster_fraction": item.get("largest_cluster_fraction")})
                checkpoint_checks.append(complete and all(
                    int(by_client[c].get("occupied_clusters", 0)) >= 2 and
                    float(by_client[c].get("largest_cluster_fraction", 1.0)) < 0.99
                    for c in range(6)) if complete else False)
            # Some runner records keep only final_metrics in summary; include
            # final per-client metrics there when round-indexed metrics absent.
            if not any(row["partition"] == partition and row["seed"] == seed
                       for row in quality_rows):
                for item in metrics:
                    quality_rows.append({"kind": "final_summary", "partition": partition,
                        "seed": seed, "round": item.get("round", 200), "client": item.get("client"),
                        "acc": item.get("acc"), "nmi": item.get("nmi"), "ari": item.get("ari"),
                        "occupied_clusters": item.get("occupied_clusters"),
                        "largest_cluster_fraction": item.get("largest_cluster_fraction")})
            quality_ok[partition][str(seed)] = (
                len(checkpoint_checks) == len(CHECKPOINTS) and all(checkpoint_checks))

            # Average each client's same-cluster edge fraction across the last
            # 40 rounds, then inspect C0 and C3 separately per seed.
            round_rows = anchor.get("round_records", [])
            last_by_round = {int(r["round"]): r for r in round_rows
                             if r.get("round") is not None and 161 <= int(r["round"]) <= 200}
            expected_rounds = set(range(161, 201))
            teacher_complete = set(last_by_round) == expected_rounds
            fractions = [_round_fraction(last_by_round[r]) for r in range(161, 201)] \
                if teacher_complete else []
            teacher_complete = teacher_complete and len(fractions) == 40 and all(
                row is not None and len(row) == 6 for row in fractions)
            teacher_values = {}
            for client, name in CLIENT_NAMES.items():
                vals = [row[client] for row in fractions if row is not None and len(row) > client]
                avg = _mean(vals) if teacher_complete and len(vals) == 40 else None
                teacher_values[name] = avg
                quality_rows.append({"kind": "teacher_fraction_last40", "partition": partition,
                    "seed": seed, "round": "161-200", "client": client,
                    "client_name": name, "teacher_same_cluster_fraction": avg})
            teacher_ok[partition][str(seed)] = teacher_complete and all(
                teacher_values[name] is not None and teacher_values[name] <= 0.40
                for name in CLIENT_NAMES.values())

    _write_csv(out / "quality.csv", quality_rows, [
        "kind", "partition", "seed", "round", "client", "client_name", "acc", "nmi", "ari",
        "occupied_clusters", "largest_cluster_fraction", "teacher_same_cluster_fraction"])
    for partition, detail in decisions.items():
        formal = not smoke and len(detail["seed_method_mean_head_pipeline_seconds"]) == 3
        detail["quality"] = {
            "cluster_guard_by_seed": quality_ok.get(partition, {}),
            "teacher_C0_C3_le_0.40_by_seed": teacher_ok.get(partition, {}),
            "pass": formal and all(quality_ok.get(partition, {}).values())
                    and all(teacher_ok.get(partition, {}).values()),
            "formal_quality_decision": formal,
        }
        detail["overall_pass"] = formal and all(detail[k]["pass"] for k in ("C1", "C2", "C3")) \
            and detail["quality"]["pass"]
    payload = {"mode": "exploratory_smoke" if smoke else "formal_confirmation",
               "statistical_unit": "seed; technical repeats averaged before paired comparisons",
               "small_sample_note": "n=3 seeds; report paired per-seed ratios and min/max only; no significance claims.",
               "partitions": decisions}
    (out / "decision.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = ["# Private-prior B/E/D confirmation report", "",
             f"Mode: **{'exploratory smoke' if smoke else 'formal confirmation'}**.", "",
             "Technical repeats are averaged within each seed and method before paired D/B and D/E comparisons. The seed is the statistical unit; n=3 is small, so this report gives per-seed ratios and their min/max without significance claims.", "",
             "Raw `head_pipeline_seconds`, measured stage time and generation time are listed for every technical repeat in `raw_runs.csv`. Shared preparation and loading costs are separate fields. Preparation is a one-time shared cost and is not added three times to a repeat total.", "",
             "Quality is reported without an ACC-improvement requirement. `quality.csv` contains client-level ACC, NMI, ARI, occupied clusters and largest-cluster fraction at rounds 160/180/200, plus C0/C3 teacher same-cluster rates averaged over rounds 161–200.", ""]
    for partition, d in decisions.items():
        lines += [f"## {partition}", "",
                  f"D/B median: {d['D_over_B_median']:.4f} (min–max {d['D_over_B_min_max'][0]:.4f}–{d['D_over_B_min_max'][1]:.4f}); C1 {'PASS' if d['C1']['pass'] else 'exploratory/not passed'}.",
                  f"D/E median: {d['D_over_E_median']:.4f} (min–max {d['D_over_E_min_max'][0]:.4f}–{d['D_over_E_min_max'][1]:.4f}); C2 {'PASS' if d['C2']['pass'] else 'exploratory/not passed'}.",
                  f"Seed wins: D beats B in {d['D_wins_vs_B']['count']}/{d['D_wins_vs_B']['seeds']}, and E in {d['D_wins_vs_E']['count']}/{d['D_wins_vs_E']['seeds']}; C3 {'PASS' if d['C3']['pass'] else 'exploratory/not passed'}.",
                  f"Quality guard: {'PASS' if d['quality']['pass'] else 'exploratory/not passed'}; overall formal decision: {'PASS' if d['overall_pass'] else 'not established'}.", "",
                  "Per-seed paired ratios: " + "; ".join(
                      f"{seed}: D/B={d['paired_ratios_D_over_B_by_seed'][seed]:.4f}, D/E={d['paired_ratios_D_over_E_by_seed'][seed]:.4f}"
                      for seed in d["paired_ratios_D_over_B_by_seed"]), ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return payload
