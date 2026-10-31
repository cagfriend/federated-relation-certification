"""CSV/JSON/Markdown reporting for collaboration-mechanism experiments.

The input is intentionally kept as ordinary Python dictionaries so the report
can preserve complete evaluation curves and diagnostics without depending on
the experiment runner's internal classes.
"""

from __future__ import annotations

import csv
import json
import math
import statistics
from pathlib import Path
from typing import Any, Iterable


METHODS = ("Local", "Self", "Aggregate", "Shuffled")
COMPARISONS = (("Aggregate", "Self"), ("Aggregate", "Shuffled"), ("Aggregate", "Local"))
PRACTICAL_THRESHOLD = 0.005
MAIN_PARTITION = "dirichlet_0.1"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=_json_default) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row:
            if key not in seen:
                fields.append(key)
                seen.add(key)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        if not fields:
            f.write("")
            return
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _csv_value(v) for k, v in row.items()})


def _csv_value(value: Any) -> Any:
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=_json_default, sort_keys=isinstance(value, dict))
    return value


def _flatten(prefix: str, value: Any, out: dict[str, Any]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten(f"{prefix}.{key}" if prefix else str(key), child, out)
    elif isinstance(value, (list, tuple)):
        out[prefix] = json.dumps(value, ensure_ascii=False, default=_json_default)
    else:
        out[prefix] = value


def _round_key(value: Any) -> tuple[int, Any]:
    try:
        return (0, float(value))
    except (TypeError, ValueError):
        return (1, str(value))


def _final_metric(case: dict[str, Any], method: str) -> dict[str, Any] | None:
    summary = case.get("summary", {}) or {}
    branch = summary.get(method, {}) or {}
    final = branch.get("final_metrics")
    if isinstance(final, dict):
        return final
    candidates = [m for m in case.get("metrics", []) if m.get("method") == method]
    return max(candidates, key=lambda m: _round_key(m.get("round"))) if candidates else None


def _partition(case: dict[str, Any]) -> str:
    return str(case.get("partition", (case.get("config", {}) or {}).get("partition", "")))


def _seed(case: dict[str, Any]) -> Any:
    return case.get("seed", (case.get("config", {}) or {}).get("seed", ""))


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _client_map(metric: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not metric:
        return {}
    return {str(c.get("client")): c for c in metric.get("clients", [])}


def _mean_acc(metric: dict[str, Any] | None) -> float | None:
    if not metric:
        return None
    mean = metric.get("mean", {}) or {}
    value = _number(mean.get("acc"))
    if value is not None:
        return value
    vals = [_number(c.get("acc")) for c in metric.get("clients", [])]
    vals = [x for x in vals if x is not None]
    return statistics.mean(vals) if vals else None


def _mean_metric(metric: dict[str, Any] | None, name: str) -> float | None:
    if not metric:
        return None
    value = _number((metric.get("mean", {}) or {}).get(name))
    if value is not None:
        return value
    vals = [_number(c.get(name)) for c in metric.get("clients", [])]
    vals = [x for x in vals if x is not None]
    return statistics.mean(vals) if vals else None


def _worst_acc(metric: dict[str, Any] | None) -> float | None:
    vals = [_number(c.get("acc")) for c in (metric or {}).get("clients", [])]
    vals = [x for x in vals if x is not None]
    return min(vals) if vals else None


def _diff(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else a - b


def _median(values: Iterable[float]) -> float | None:
    values = list(values)
    return statistics.median(values) if values else None


def _range(values: Iterable[float]) -> tuple[float | None, float | None]:
    values = list(values)
    return (min(values), max(values)) if values else (None, None)


def _paired_quality_for_partition(cases: list[dict[str, Any]], partition: str, primary: bool) -> list[dict[str, Any]]:
    """Create client detail, seed-level, and across-seed inference rows.

    Client observations are paired within seed. Across-seed summaries operate
    only on one seed-level value per seed, avoiding client-level pseudoreplication.
    """
    partition_cases = [c for c in cases if _partition(c) == partition]
    all_full = bool(partition_cases) and all((c.get("identity", {}) or {}).get("preset") == "full" for c in partition_cases)
    has_smoke = any((c.get("identity", {}) or {}).get("preset") == "smoke" for c in partition_cases)
    rows: list[dict[str, Any]] = []
    for lhs, rhs in COMPARISONS:
        seed_rows: list[dict[str, Any]] = []
        for case in sorted(partition_cases, key=lambda c: str(_seed(c))):
            lm, rm = _final_metric(case, lhs), _final_metric(case, rhs)
            lmap, rmap = _client_map(lm), _client_map(rm)
            common = sorted(set(lmap) & set(rmap))
            client_diffs: list[float] = []
            client_metric_diffs = {name: [] for name in ("nmi", "ari")}
            for client in common:
                la, ra = _number(lmap[client].get("acc")), _number(rmap[client].get("acc"))
                delta = _diff(la, ra)
                metric_deltas = {name: _diff(_number(lmap[client].get(name)), _number(rmap[client].get(name)))
                                 for name in ("nmi", "ari")}
                for name, value in metric_deltas.items():
                    if value is not None:
                        client_metric_diffs[name].append(value)
                if delta is not None:
                    client_diffs.append(delta)
                    rows.append({
                        "row_type": "client_pair", "partition": _partition(case), "seed": _seed(case),
                        "comparison": f"{lhs}-{rhs}", "lhs": lhs, "rhs": rhs, "client": client,
                        "lhs_acc": la, "rhs_acc": ra, "acc_diff": delta,
                        "lhs_nmi": _number(lmap[client].get("nmi")), "rhs_nmi": _number(rmap[client].get("nmi")),
                        "nmi_diff": metric_deltas["nmi"],
                        "lhs_ari": _number(lmap[client].get("ari")), "rhs_ari": _number(rmap[client].get("ari")),
                        "ari_diff": metric_deltas["ari"],
                        "benefit_gt_0": delta > 0, "harm_lt_0": delta < 0,
                        "benefit_ge_0.005": delta >= PRACTICAL_THRESHOLD,
                    })
                elif any(value is not None for value in metric_deltas.values()):
                    rows.append({
                        "row_type": "client_pair", "partition": _partition(case), "seed": _seed(case),
                        "comparison": f"{lhs}-{rhs}", "lhs": lhs, "rhs": rhs, "client": client,
                        "lhs_acc": la, "rhs_acc": ra, "acc_diff": None,
                        "lhs_nmi": _number(lmap[client].get("nmi")), "rhs_nmi": _number(rmap[client].get("nmi")),
                        "nmi_diff": metric_deltas["nmi"],
                        "lhs_ari": _number(lmap[client].get("ari")), "rhs_ari": _number(rmap[client].get("ari")),
                        "ari_diff": metric_deltas["ari"],
                    })
            denominator = len(client_diffs)
            lmean, rmean = _mean_acc(lm), _mean_acc(rm)
            nmi_diff = _diff(_mean_metric(lm, "nmi"), _mean_metric(rm, "nmi"))
            ari_diff = _diff(_mean_metric(lm, "ari"), _mean_metric(rm, "ari"))
            # Use reported final mean ACC for the primary mean difference; preserve
            # per-client paired deltas separately above.
            mean_diff = _diff(lmean, rmean)
            worst_diff = _diff(_worst_acc(lm), _worst_acc(rm))
            seed_row = {
                "partition": _partition(case), "seed": _seed(case), "comparison": f"{lhs}-{rhs}",
                "lhs": lhs, "rhs": rhs, "client_pairs": denominator,
                "mean_acc_diff": mean_diff, "paired_client_mean_diff": statistics.mean(client_diffs) if client_diffs else None,
                "mean_nmi_diff": nmi_diff, "paired_client_mean_nmi_diff": statistics.mean(client_metric_diffs["nmi"]) if client_metric_diffs["nmi"] else None,
                "mean_ari_diff": ari_diff, "paired_client_mean_ari_diff": statistics.mean(client_metric_diffs["ari"]) if client_metric_diffs["ari"] else None,
                "worst_acc_diff": worst_diff,
                "client_benefit_gt_0_count": sum(d > 0 for d in client_diffs),
                "client_harm_lt_0_count": sum(d < 0 for d in client_diffs),
                "client_benefit_ge_0.005_count": sum(d >= PRACTICAL_THRESHOLD for d in client_diffs),
                "client_benefit_gt_0_rate": sum(d > 0 for d in client_diffs) / denominator if denominator else None,
                "client_harm_lt_0_rate": sum(d < 0 for d in client_diffs) / denominator if denominator else None,
                "client_benefit_ge_0.005_rate": sum(d >= PRACTICAL_THRESHOLD for d in client_diffs) / denominator if denominator else None,
            }
            seed_rows.append(seed_row)
            rows.append({"row_type": "seed_summary", **seed_row})

        mean_diffs = [r["mean_acc_diff"] for r in seed_rows if r["mean_acc_diff"] is not None]
        worst_diffs = [r["worst_acc_diff"] for r in seed_rows if r["worst_acc_diff"] is not None]
        paired_diffs = [r["paired_client_mean_diff"] for r in seed_rows if r["paired_client_mean_diff"] is not None]
        nmi_diffs = [r["mean_nmi_diff"] for r in seed_rows if r["mean_nmi_diff"] is not None]
        ari_diffs = [r["mean_ari_diff"] for r in seed_rows if r["mean_ari_diff"] is not None]
        num_seeds = len(seed_rows)
        is_primary_comparison = primary and lhs == "Aggregate" and rhs in ("Self", "Shuffled")
        criterion_met = (all_full and num_seeds == 3 and len(mean_diffs) == 3 and all(d > 0 for d in mean_diffs)
                         and _median(mean_diffs) is not None and _median(mean_diffs) >= PRACTICAL_THRESHOLD)
        if has_smoke:
            status = "smoke仅路径验证，不作门槛判定"
        elif is_primary_comparison:
            status = "探索筛查门槛达到，仍需新seed确认" if criterion_met else ("未完成" if num_seeds < 3 else "探索筛查门槛未达到")
        else:
            status = "次要描述性比较"
        lo, hi = _range(mean_diffs)
        rows.append({
            "row_type": "across_seed_summary", "partition": partition, "comparison": f"{lhs}-{rhs}",
            "lhs": lhs, "rhs": rhs, "num_seeds": num_seeds, "valid_mean_diff_seeds": len(mean_diffs),
            "median_mean_acc_diff": _median(mean_diffs), "positive_mean_diff_seeds": sum(d > 0 for d in mean_diffs),
            "mean_acc_diff_min": lo, "mean_acc_diff_max": hi,
            "median_mean_nmi_diff": _median(nmi_diffs), "positive_mean_nmi_diff_seeds": sum(d > 0 for d in nmi_diffs),
            "mean_nmi_diff_min": _range(nmi_diffs)[0], "mean_nmi_diff_max": _range(nmi_diffs)[1],
            "median_mean_ari_diff": _median(ari_diffs), "positive_mean_ari_diff_seeds": sum(d > 0 for d in ari_diffs),
            "mean_ari_diff_min": _range(ari_diffs)[0], "mean_ari_diff_max": _range(ari_diffs)[1],
            "median_worst_acc_diff": _median(worst_diffs),
            "positive_worst_acc_diff_seeds": sum(d > 0 for d in worst_diffs),
            "worst_acc_diff_min": _range(worst_diffs)[0], "worst_acc_diff_max": _range(worst_diffs)[1],
            "median_paired_client_mean_diff_seed_level": _median(paired_diffs),
            "median_client_benefit_gt_0_rate_seed_level": _median(r["client_benefit_gt_0_rate"] for r in seed_rows if r["client_benefit_gt_0_rate"] is not None),
            "median_client_harm_lt_0_rate_seed_level": _median(r["client_harm_lt_0_rate"] for r in seed_rows if r["client_harm_lt_0_rate"] is not None),
            "median_client_benefit_ge_0.005_rate_seed_level": _median(r["client_benefit_ge_0.005_rate"] for r in seed_rows if r["client_benefit_ge_0.005_rate"] is not None),
            "preregistered_threshold": PRACTICAL_THRESHOLD, "screening_status": status,
        })
    primary_rows = [r for r in rows if primary and all_full and not has_smoke and r.get("row_type") == "across_seed_summary"
                    and r.get("comparison") in ("Aggregate-Self", "Aggregate-Shuffled")]
    joint_pass = len(primary_rows) == 2 and all(
        r.get("num_seeds", 0) == 3 and r.get("valid_mean_diff_seeds", 0) == 3
        and r.get("positive_mean_diff_seeds", 0) == 3
        and r.get("median_mean_acc_diff") is not None
        and r["median_mean_acc_diff"] >= PRACTICAL_THRESHOLD
        for r in primary_rows
    )
    for row in primary_rows:
        if joint_pass:
            row["screening_status"] = "探索筛查门槛达到，仍需新seed确认"
        elif row.get("num_seeds", 0) < 3:
            row["screening_status"] = "未完成"
        else:
            row["screening_status"] = "探索筛查门槛未达到"
    return rows


def _paired_quality(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    partitions = sorted({_partition(case) for case in cases})
    rows: list[dict[str, Any]] = []
    for partition in partitions:
        rows.extend(_paired_quality_for_partition(cases, partition, partition == MAIN_PARTITION))
    return rows


def _summary_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        base = {"case_index": index, "partition": _partition(case), "seed": _seed(case)}
        _flatten("config", case.get("config", {}) or {}, base)
        summary = case.get("summary", {}) or {}
        for method in METHODS:
            branch = summary.get(method)
            if not isinstance(branch, dict):
                continue
            row = dict(base, method=method)
            final = branch.get("final_metrics") or _final_metric(case, method) or {}
            row["final_round"] = final.get("round")
            _flatten("final", {k: final.get(k) for k in ("mean",) if k in final}, row)
            for key in ("head_pipeline_seconds", "generation_seconds", "private_seconds", "public_seconds", "exchange_seconds", "traffic", "final_head_digest"):
                if key in branch:
                    _flatten(key, branch[key], row)
            rows.append(row)
    return rows


def _final_client_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        for method in METHODS:
            metric = _final_metric(case, method)
            if not metric:
                continue
            for client in metric.get("clients", []):
                rows.append({"case_index": index, "partition": _partition(case), "seed": _seed(case),
                             "method": method, "round": metric.get("round"), **client})
    return rows


def _diagnostic_rows(cases: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    rows = []
    for index, case in enumerate(cases):
        for entry in case.get(key, []) or []:
            rows.append({"case_index": index, "partition": _partition(case), "seed": _seed(case), **entry})
    return rows


def _markdown(cases: list[dict[str, Any]], paired: list[dict[str, Any]]) -> str:
    partitions = sorted({_partition(c) for c in cases})
    lines = ["# Collaboration mechanism experiment report", "",
             "**Scope:** This report is exploratory and is not performance confirmation for D/E.",
             "Local uses no public update. The other branches use a fixed public budget. Self and Aggregate may follow different trajectories; their per-round curves are retained as observed.",
             "Case summary timings are diagnostics only and do not support formal performance inferences.", "",
             "Formal exploratory screening applies only when every case in the partition has `identity.preset == full`; smoke runs validate the path only and cannot determine the screening threshold.", "",
             f"Cases: {len(cases)}. Partitions: {', '.join(partitions) if partitions else 'none'}.", "",
             f"Primary scenario: `{MAIN_PARTITION}`; primary metric: final mean ACC. Preregistered exploratory practical threshold: {PRACTICAL_THRESHOLD:.3f} (0.5 percentage points).", "",
             "The screening label requires exactly three seed-level Aggregate−Self and Aggregate−Shuffled mean-ACC differences, all positive, with each comparison's median at least 0.005. It is a screening label only; new seeds are required for confirmation.", "",
             "ACC alone determines the screening label. NMI and ARI are secondary paired metrics.", "",
             "## Paired seed summaries by partition", "",
             "| Partition | Role | Comparison | Seeds | Median mean-ACC diff | Positive ACC seeds | ACC range | Median worst-ACC diff | Median mean-NMI diff | Positive NMI seeds | Median mean-ARI diff | Positive ARI seeds | Screening |",
             "|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|"]
    for row in paired:
        if row.get("row_type") != "across_seed_summary":
            continue
        fmt = lambda x: "—" if x is None else f"{x:.4f}"
        role = "主场景" if row.get("partition") == MAIN_PARTITION else "次要场景"
        lines.append(f"| {row.get('partition', '')} | {role} | {row['comparison']} | {row.get('num_seeds', 0)} | {fmt(row.get('median_mean_acc_diff'))} | {row.get('positive_mean_diff_seeds', 0)} | {fmt(row.get('mean_acc_diff_min'))} to {fmt(row.get('mean_acc_diff_max'))} | {fmt(row.get('median_worst_acc_diff'))} | {fmt(row.get('median_mean_nmi_diff'))} | {row.get('positive_mean_nmi_diff_seeds', 0)} | {fmt(row.get('median_mean_ari_diff'))} | {row.get('positive_mean_ari_diff_seeds', 0)} | {row.get('screening_status', '')} |")
    lines += ["", "## Evaluation curves", "", "The complete per-round evaluation curves for every supplied case are preserved in `summary.json`; no round or scenario is selected by its best score.", ""]
    return "\n".join(lines)


def reports(output: Path, cases: list[dict[str, Any]]) -> None:
    """Write all experiment reports into *output*.

    Expected case keys are ``partition``, ``seed``, ``config``, ``metrics``,
    ``summary``, ``diagnostics`` and ``target_records``. Diagnostic record
    columns are discovered dynamically so evolving instrumentation fields are
    retained.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = list(cases)
    paired = _paired_quality(cases)
    compact_cases = [{"partition": _partition(case), "seed": _seed(case),
                      "config": case.get("config", {}), "summary": case.get("summary", {}),
                      "metrics": case.get("metrics", [])} for case in cases]
    _write_json(output / "summary.json", {"cases": compact_cases, "paired_quality": paired,
                                          "report_scope": {"primary_partition": MAIN_PARTITION,
                                                           "primary_metric": "final mean ACC",
                                                           "preregistered_threshold": PRACTICAL_THRESHOLD,
                                                           "formal_screening_requires_all_partition_cases_preset_full": True,
                                                           "case_timings_are_diagnostic_only": True,
                                                           "not_D_or_E_performance_confirmation": True}})
    _write_csv(output / "summary.csv", _summary_rows(cases))
    _write_csv(output / "final_clients.csv", _final_client_rows(cases))
    _write_csv(output / "paired_quality.csv", paired)
    _write_csv(output / "diagnostics.csv", _diagnostic_rows(cases, "diagnostics"))
    _write_csv(output / "target_diagnostics.csv", _diagnostic_rows(cases, "target_records"))
    (output / "report.md").write_text(_markdown(cases, paired), encoding="utf-8")

