"""Reports for the public-budget experiment.

Input cases are the compact result objects produced by the experiment runner.
The reporter deliberately keeps pairing within partition, case and seed.
"""

import csv
import json
import math
import statistics
from pathlib import Path

from .design import QUALITY_ACC_DROP


METHODS = ("B", "E", "D")
TIME_FIELDS = (
    "initialization_seconds",
    "private_seconds",
    "generation_seconds",
    "exchange_seconds",
    "public_seconds",
    "head_pipeline_seconds",
    "with_shared_preparation_seconds",
)
METRICS = ("acc", "nmi", "ari")
TRAFFIC_FIELDS = ("total_bytes",)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _num(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def _id(case):
    if case.get("case_id") is not None:
        return str(case["case_id"])
    return "unspecified"


def _key(case):
    return (str(case.get("partition", "")), case.get("seed"), _id(case))


def _sort_seed(value):
    return (value is None, str(value))


def _write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _case_config(case):
    return case.get("config") or (case.get("spec") or {}).get("config") or {}


def _effective_steps(case, summary=None):
    spec = case.get("spec") or {}
    if spec.get("policy") == "fixed" and spec.get("steps") is not None:
        return spec.get("steps")
    config = _case_config(case)
    samples = config.get("samples", config.get("m"))
    batch = config.get("public_edge_batch")
    degree = config.get("degree")
    if all(_num(x) and x > 0 for x in (samples, batch, degree)):
        edge_count = int(samples * degree // 2)
        return (edge_count + int(batch) - 1) // int(batch)
    # Fallback for compact or older configs that omit the edge batch setting.
    rounds = config.get("rounds")
    dimensions = config.get("dimensions")
    optimizer_steps = (summary or {}).get("public_optimizer_steps")
    if _num(rounds) and rounds > 0 and isinstance(dimensions, (list, tuple)) and dimensions and _num(optimizer_steps):
        denom = rounds * len(dimensions)
        if denom and optimizer_steps % denom == 0:
            return int(optimizer_steps // denom)
    return None


def _method_rows(cases):
    rows = []
    for case in cases:
        config = _case_config(case)
        spec = case.get("spec") or {}
        for method in METHODS:
            summary = (case.get("summary") or {}).get(method)
            if not summary:
                continue
            final = summary.get("final_metrics") or {}
            mean = final.get("mean") or {}
            traffic = summary.get("traffic") or {}
            row = {
                "partition": case.get("partition"), "seed": case.get("seed"),
                "case_id": _id(case), "method": method,
                "policy": spec.get("policy"), "steps": _effective_steps(case, summary),
                "samples": config.get("samples", config.get("m")),
                "head_pipeline_seconds": summary.get("head_pipeline_seconds"),
                "with_shared_preparation_seconds": summary.get("with_shared_preparation_seconds"),
                "initialization_seconds": summary.get("initialization_seconds"),
                "private_seconds": summary.get("private_seconds"),
                "generation_seconds": summary.get("generation_seconds"),
                "exchange_seconds": summary.get("exchange_seconds"),
                "public_seconds": summary.get("public_seconds"),
                "teacher_recompute_fraction": summary.get("teacher_recompute_fraction"),
                "generation_fraction": summary.get("generation_fraction"),
                "persistent_method_array_bytes": summary.get("persistent_method_array_bytes"),
                "traffic_total_bytes": traffic.get("total_bytes"),
                **{metric: mean.get(metric) for metric in METRICS},
                "final_head_digest": summary.get("final_head_digest"),
                "public_optimizer_steps": summary.get("public_optimizer_steps"),
                "student_forward_endpoints": _json(summary.get("student_forward_endpoints", [])),
            }
            rows.append(row)
    return rows


def _paired_cost(cases):
    by_group = {}
    for case in cases:
        key = _key(case)
        if key in by_group:
            raise ValueError(f"duplicate partition/seed/case_id: {key}")
        by_group[key] = case
    rows = []
    for (partition, seed, case_id), case in sorted(by_group.items(), key=lambda x: (x[0][0], _sort_seed(x[0][1]), x[0][2])):
        summaries = case.get("summary") or {}
        for reference in ("B", "E"):
            d, ref = summaries.get("D") or {}, summaries.get(reference) or {}
            for field in TIME_FIELDS:
                dv, rv = d.get(field), ref.get(field)
                paired = _num(dv) and _num(rv) and rv != 0
                rows.append({
                    "partition": partition, "seed": seed, "case_id": case_id,
                    "comparison": f"D_over_{reference}", "measure": field,
                    "paired": paired,
                    "D_seconds": dv, "reference_seconds": rv,
                    "ratio_D_over_reference": dv / rv if paired else "",
                    "seconds_saved_reference_minus_D": rv - dv if paired else "",
                    "D_teacher_recompute_fraction": d.get("teacher_recompute_fraction"),
                    "reference_teacher_recompute_fraction": ref.get("teacher_recompute_fraction"),
                    "D_generation_fraction": d.get("generation_fraction"),
                    "reference_generation_fraction": ref.get("generation_fraction"),
                    "D_persistent_method_array_bytes": d.get("persistent_method_array_bytes"),
                    "reference_persistent_method_array_bytes": ref.get("persistent_method_array_bytes"),
                    "D_minus_reference_persistent_method_array_bytes": (
                        d.get("persistent_method_array_bytes") - ref.get("persistent_method_array_bytes")
                        if _num(d.get("persistent_method_array_bytes")) and _num(ref.get("persistent_method_array_bytes")) else ""),
                    "D_traffic_total_bytes": (d.get("traffic") or {}).get("total_bytes"),
                    "reference_traffic_total_bytes": (ref.get("traffic") or {}).get("total_bytes"),
                    "D_minus_reference_traffic_total_bytes": (
                        (d.get("traffic") or {}).get("total_bytes") - (ref.get("traffic") or {}).get("total_bytes")
                        if _num((d.get("traffic") or {}).get("total_bytes")) and _num((ref.get("traffic") or {}).get("total_bytes")) else ""),
                })
    return rows


def _quality_guardrails(cases):
    """Compare B's fixed-budget result with B's same-M full-budget result."""
    index = {}
    for case in cases:
        config, spec = _case_config(case), case.get("spec") or {}
        samples = config.get("samples", config.get("m"))
        policy = spec.get("policy")
        steps = spec.get("steps")
        if samples is None:
            continue
        index.setdefault((str(case.get("partition", "")), case.get("seed"), samples), {})[policy] = (case, steps)
    out = []
    for (partition, seed, samples), policies in sorted(index.items(), key=lambda x: (x[0][0], _sort_seed(x[0][1]), str(x[0][2]))):
        fixed = [(c, s) for p, (c, s) in policies.items() if p == "fixed"]
        full = [(c, s) for p, (c, s) in policies.items() if p == "full"]
        for fixed_case, fixed_steps in fixed:
            for full_case, full_steps in full:
                fb = (fixed_case.get("summary") or {}).get("B") or {}
                ub = (full_case.get("summary") or {}).get("B") or {}
                fm = (fb.get("final_metrics") or {}).get("mean") or {}
                um = (ub.get("final_metrics") or {}).get("mean") or {}
                diffs = {metric: (fm.get(metric) - um.get(metric)
                                  if _num(fm.get(metric)) and _num(um.get(metric)) else None)
                         for metric in METRICS}
                acc_delta = diffs["acc"]
                out.append({
                    "partition": partition, "seed": seed, "samples": samples,
                    "fixed_case_id": _id(fixed_case), "fixed_steps": _effective_steps(fixed_case, fb),
                    "full_case_id": _id(full_case), "full_steps": _effective_steps(full_case, ub),
                    "method": "B", "comparison": "fixed_minus_full",
                    "fixed_acc": fm.get("acc"), "full_acc": um.get("acc"), "acc_delta": acc_delta,
                    "acc_drop": -acc_delta if _num(acc_delta) else None,
                    "within_acc_guardrail": (bool(acc_delta >= -QUALITY_ACC_DROP - 1e-12) if _num(acc_delta) else "pending"),
                    "fixed_nmi": fm.get("nmi"), "full_nmi": um.get("nmi"), "nmi_delta": diffs["nmi"],
                    "fixed_ari": fm.get("ari"), "full_ari": um.get("ari"), "ari_delta": diffs["ari"],
                    **_client_acc_deltas(fb, ub),
                    "status": "paired" if all(_num(fm.get(m)) and _num(um.get(m)) for m in METRICS) else "pending_incomplete_metrics",
                })
    # Explicitly retain unmatched fixed cases as pending rather than silently dropping them.
    matched = {(r["partition"], r["seed"], r["samples"], r["fixed_case_id"]) for r in out}
    for case in cases:
        spec, config = case.get("spec") or {}, _case_config(case)
        samples = config.get("samples", config.get("m"))
        if spec.get("policy") != "fixed" or samples is None:
            continue
        key = (str(case.get("partition", "")), case.get("seed"), samples, _id(case))
        if key not in matched:
            out.append({"partition": key[0], "seed": key[1], "samples": samples,
                        "fixed_case_id": key[3], "fixed_steps": spec.get("steps"),
                        "full_case_id": "", "full_steps": "", "method": "B",
                        "comparison": "fixed_minus_full", "within_acc_guardrail": "pending",
                        "worst_client_acc_delta": None, "min_same_client_acc_delta": None,
                        "status": "pending_missing_full_match"})
    return out


def _budget_effects(cases):
    """Compare fixed/full budgets for each method at matched partition/seed/M."""
    grouped = {}
    for case in cases:
        config, spec = _case_config(case), case.get("spec") or {}
        samples = config.get("samples", config.get("m"))
        policy = spec.get("policy")
        if samples is not None and policy in ("full", "fixed"):
            grouped.setdefault((str(case.get("partition", "")), case.get("seed"), samples), {})[policy] = case
    rows = []
    for (partition, seed, samples), policies in sorted(grouped.items(), key=lambda x: (x[0][0], _sort_seed(x[0][1]), str(x[0][2]))):
        full_case, fixed_case = policies.get("full"), policies.get("fixed")
        if not full_case or not fixed_case:
            continue
        for method in METHODS:
            full = (full_case.get("summary") or {}).get(method) or {}
            fixed = (fixed_case.get("summary") or {}).get(method) or {}
            if not full or not fixed:
                continue
            row = {"partition": partition, "seed": seed, "samples": samples,
                   "method": method, "full_case_id": _id(full_case), "fixed_case_id": _id(fixed_case),
                   "full_steps": _effective_steps(full_case, full), "fixed_steps": _effective_steps(fixed_case, fixed),
                   "generation_fraction_full": full.get("generation_fraction"),
                   "generation_fraction_fixed": fixed.get("generation_fraction"),
                   "generation_fraction_change_fixed_minus_full": (
                       fixed.get("generation_fraction") - full.get("generation_fraction")
                       if _num(fixed.get("generation_fraction")) and _num(full.get("generation_fraction")) else ""),
                   "public_optimizer_steps_full": full.get("public_optimizer_steps"),
                   "public_optimizer_steps_fixed": fixed.get("public_optimizer_steps"),
                   "public_optimizer_steps_change_fixed_minus_full": (
                       fixed.get("public_optimizer_steps") - full.get("public_optimizer_steps")
                       if _num(fixed.get("public_optimizer_steps")) and _num(full.get("public_optimizer_steps")) else "")}
            for phase in ("head_pipeline_seconds", "with_shared_preparation_seconds"):
                fv, xv = full.get(phase), fixed.get(phase)
                row[f"{phase}_full"] = fv
                row[f"{phase}_fixed"] = xv
                paired = _num(fv) and _num(xv) and fv != 0
                row[f"{phase}_fixed_over_full"] = xv / fv if paired else ""
                row[f"{phase}_saved_seconds_full_minus_fixed"] = fv - xv if paired else ""
            rows.append(row)
    return rows


def _client_acc_deltas(fixed_summary, full_summary):
    fc = (fixed_summary.get("final_metrics") or {}).get("clients") or []
    uc = (full_summary.get("final_metrics") or {}).get("clients") or []
    fmap = {x.get("client"): x.get("acc") for x in fc}
    umap = {x.get("client"): x.get("acc") for x in uc}
    shared = [fmap[k] - umap[k] for k in fmap.keys() & umap.keys()
              if _num(fmap[k]) and _num(umap[k])]
    fixed_accs = [x.get("acc") for x in fc if _num(x.get("acc"))]
    full_accs = [x.get("acc") for x in uc if _num(x.get("acc"))]
    worst_delta = min(fixed_accs) - min(full_accs) if fixed_accs and full_accs else None
    return {"worst_client_acc_delta": worst_delta,
            "min_same_client_acc_delta": min(shared) if shared else None}


def _client_rows(cases):
    rows = []
    for case in cases:
        for method, summary in (case.get("summary") or {}).items():
            clients = ((summary.get("final_metrics") or {}).get("clients") or [])
            for client in clients:
                rows.append({"partition": case.get("partition"), "seed": case.get("seed"),
                             "case_id": _id(case), "method": method, **client})
    return rows


def _memory_rows(profiles):
    return [{"partition": p.get("partition"), "seed": p.get("seed"),
             "case_id": p.get("case_id"), "method": p.get("method"),
             "process_peak_working_set_bytes": p.get("process_peak_working_set_bytes"),
             "persistent_method_array_bytes": p.get("persistent_method_array_bytes"),
             "final_head_digest": p.get("final_head_digest")} for p in profiles]


def _summary_stats(cases, paired_rows, guardrails, profiles):
    groups = {}
    for row in paired_rows:
        key = (row["partition"], row["case_id"], row["comparison"], row["measure"])
        groups.setdefault(key, []).append(row)
    aggregate = []
    for key, items in sorted(groups.items()):
        paired = [r for r in items if r["paired"]]
        ratios = [r["ratio_D_over_reference"] for r in paired]
        savings = [r["seconds_saved_reference_minus_D"] for r in paired]
        aggregate.append({"partition": key[0], "case_id": key[1], "comparison": key[2], "measure": key[3],
                          "paired_seeds": len(paired), "wins_D_faster": sum(x < 1 for x in ratios),
                          "median_ratio_D_over_reference": statistics.median(ratios) if ratios else None,
                          "median_seconds_saved": statistics.median(savings) if savings else None,
                          "paired_seed_values": [r["seed"] for r in paired]})
    return aggregate


def _markdown(cases, aggregate, guardrails, budget_effects, profiles):
    lines = ["# 公共预算实验报告", "",
             "所有性能对照先在同一 partition、case 和 seed 内配对，再对 seed 级结果取中位数。客户端是 seed 内观测，不视为独立 seed。三 seed 结果仅为探索性配对计时，不是独立新 seed 或隔离进程的性能确认；这里不与历史的其他机器运行时间比较。", "",
             "## 配置与覆盖", "",
             "| partition | case_id | seed | policy | steps | methods |", "|:--|:--|--:|:--|--:|:--|"]
    for c in sorted(cases, key=lambda x: (str(x.get("partition")), _sort_seed(x.get("seed")), _id(x))):
        spec = c.get("spec") or {}
        summary = (c.get("summary") or {}).get("B") or {}
        actual_steps = _effective_steps(c, summary)
        lines.append(f"| {c.get('partition','')} | {_id(c)} | {c.get('seed','')} | {spec.get('policy','')} | {actual_steps if actual_steps is not None else ''} | {', '.join(m for m in METHODS if m in (c.get('summary') or {}))} |")
    primary_costs = {"generation_seconds", "head_pipeline_seconds", "with_shared_preparation_seconds"}
    primary_aggregate = [r for r in aggregate if r["measure"] in primary_costs]
    lines += ["", "## D 相对 B/E 的配对成本", "", "比值小于 1 表示 D 较快；省时为参照方法秒数减 D 秒数。下表优先显示 generation、完整 head 与 C0+head；其他阶段耗时保留在 `paired_cost.csv` 和 `summary.json`。统计以 seed 为单位。", "",
              "| partition | case_id | 对照 | 指标 | 配对 seeds | D 较快次数 | 中位比值 | 中位省秒 |", "|:--|:--|:--|:--|--:|--:|--:|--:|"]
    for r in primary_aggregate:
        ratio = "" if r["median_ratio_D_over_reference"] is None else f"{r['median_ratio_D_over_reference']:.4f}"
        saved = "" if r["median_seconds_saved"] is None else f"{r['median_seconds_saved']:.4f}"
        lines.append(f"| {r['partition']} | {r['case_id']} | {r['comparison']} | {r['measure']} | {r['paired_seeds']} | {r['wins_D_faster']} | {ratio} | {saved} |")
    lines += ["", "## 持久数组与通信量配对差", "",
              "下表按同 case、同 seed 计算 D 减参照方法；负值表示 D 使用更少的持久数组字节或 traffic。", "",
              "| partition | case_id | 对照 | paired seeds | 持久数组差中位数 bytes | traffic 差中位数 bytes |", "|:--|:--|:--|--:|--:|--:|"]
    cases_by_key = {(str(c.get("partition", "")), _id(c)): [] for c in cases}
    for c in cases:
        cases_by_key.setdefault((str(c.get("partition", "")), _id(c)), []).append(c)
    for (partition, case_id), members in sorted(cases_by_key.items()):
        for reference in ("B", "E"):
            arr, traffic = [], []
            for c in members:
                sm = c.get("summary") or {}
                d, ref = sm.get("D") or {}, sm.get(reference) or {}
                dv, rv = d.get("persistent_method_array_bytes"), ref.get("persistent_method_array_bytes")
                tv, tr = (d.get("traffic") or {}).get("total_bytes"), (ref.get("traffic") or {}).get("total_bytes")
                if _num(dv) and _num(rv): arr.append(dv-rv)
                if _num(tv) and _num(tr): traffic.append(tv-tr)
            if arr or traffic:
                av = statistics.median(arr) if arr else None
                tv = statistics.median(traffic) if traffic else None
                lines.append(f"| {partition} | {case_id} | D_over_{reference} | {min(len(arr), len(traffic))} | {av if av is not None else ''} | {tv if tv is not None else ''} |")
    lines += ["", "## 固定预算带来的预算变化", "",
              "下表比较同 partition/seed/M 下 fixed 与 full 的 B/E/D 阶段成本和学生步数；该变化来自减少学生预算，不能归因成 D 认证机制本身的贡献。", "",
              "| partition | seed | M | method | steps full→fixed | head省秒 | C0+head省秒 | generation fraction 变化 | public steps 变化 |", "|:--|--:|--:|:--|:--|--:|--:|--:|--:|"]
    for r in budget_effects:
        def fmt(x): return f"{x:.4f}" if _num(x) else ""
        lines.append(f"| {r['partition']} | {r['seed']} | {r['samples']} | {r['method']} | {r.get('full_steps','')}→{r.get('fixed_steps','')} | {fmt(r.get('head_pipeline_seconds_saved_seconds_full_minus_fixed'))} | {fmt(r.get('with_shared_preparation_seconds_saved_seconds_full_minus_fixed'))} | {fmt(r.get('generation_fraction_change_fixed_minus_full'))} | {r.get('public_optimizer_steps_change_fixed_minus_full','')} |")
    lines += ["", "## ACC 质量护栏：固定预算对同 M full", "",
              f"使用 B 的最终指标作精确配对；ACC 下降不超过 {QUALITY_ACC_DROP:g}（1 个百分点）记为 within guardrail（含 1e-12 浮点容差）。NMI、ARI、最差客户端 ACC 和同客户端最小 ACC 变化作为描述性结果。缺少同 partition/seed/M 的 full 或必要指标时标为 pending。护栏是容忍范围，不是要求质量提升。", "",
              "| partition | seed | M | fixed | full | ACC fixed−full | 护栏 | NMI 差 | ARI 差 | 最差ACC差 | 同客户端最小ACC差 | 状态 |", "|:--|--:|--:|:--|:--|--:|:--|--:|--:|--:|--:|:--|"]
    for r in guardrails:
        def fmt(x): return f"{x:.4f}" if _num(x) else ""
        lines.append(f"| {r.get('partition','')} | {r.get('seed','')} | {r.get('samples','')} | {r.get('fixed_case_id','')} | {r.get('full_case_id','')} | {fmt(r.get('acc_delta'))} | {r.get('within_acc_guardrail','pending')} | {fmt(r.get('nmi_delta'))} | {fmt(r.get('ari_delta'))} | {fmt(r.get('worst_client_acc_delta'))} | {fmt(r.get('min_same_client_acc_delta'))} | {r.get('status','')} |")
    lines += ["", "## 成本解释与边界", "",
              "`head_pipeline_seconds` 是完整 head 流程耗时；`with_shared_preparation_seconds` 是包含共享准备的总口径。另列初始化、private、generation、exchange、public 阶段耗时。generation_fraction 与 teacher_recompute_fraction 用于解释证书生成占比和 teacher 刷新成本。新增持久数组内存及 traffic 按方法逐 case/seed 输出。隔离内存档案只在提供 profile 时报告。", "",
              "这些数据用于评估主贡献的计算节省，允许小幅 ACC 回落；不将协作质量提升设为主要门槛，也不构成独立新 seed 的性能确认。", "",
              f"隔离内存 profiles：{len(profiles)}。", ""]
    return "\n".join(lines)


def reports(output: Path, cases: list, profiles: list):
    """Write the requested CSV, JSON and Markdown reports."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = list(cases or [])
    profiles = list(profiles or [])
    summary_rows = _method_rows(cases)
    paired_rows = _paired_cost(cases)
    guardrails = _quality_guardrails(cases)
    client_rows = _client_rows(cases)
    memory_rows = _memory_rows(profiles)
    budget_effects = _budget_effects(cases)
    summary_fields = ["partition", "seed", "case_id", "method", "policy", "steps", "samples",
                      *TIME_FIELDS, "teacher_recompute_fraction", "generation_fraction",
                      "persistent_method_array_bytes", "traffic_total_bytes", *METRICS,
                      "final_head_digest", "public_optimizer_steps", "student_forward_endpoints"]
    paired_fields = ["partition", "seed", "case_id", "comparison", "measure", "paired", "D_seconds",
                     "reference_seconds", "ratio_D_over_reference", "seconds_saved_reference_minus_D",
                     "D_teacher_recompute_fraction", "reference_teacher_recompute_fraction",
                     "D_generation_fraction", "reference_generation_fraction",
                     "D_persistent_method_array_bytes", "reference_persistent_method_array_bytes",
                     "D_minus_reference_persistent_method_array_bytes", "D_traffic_total_bytes",
                     "reference_traffic_total_bytes", "D_minus_reference_traffic_total_bytes"]
    quality_fields = ["partition", "seed", "samples", "fixed_case_id", "fixed_steps", "full_case_id",
                      "full_steps", "method", "comparison", "fixed_acc", "full_acc", "acc_delta", "acc_drop",
                      "within_acc_guardrail", "fixed_nmi", "full_nmi", "nmi_delta", "fixed_ari", "full_ari",
                      "ari_delta", "worst_client_acc_delta", "min_same_client_acc_delta", "status"]
    budget_fields = ["partition", "seed", "samples", "method", "full_case_id", "fixed_case_id", "full_steps", "fixed_steps",
                     "head_pipeline_seconds_full", "head_pipeline_seconds_fixed", "head_pipeline_seconds_fixed_over_full",
                     "head_pipeline_seconds_saved_seconds_full_minus_fixed", "with_shared_preparation_seconds_full",
                     "with_shared_preparation_seconds_fixed", "with_shared_preparation_seconds_fixed_over_full",
                     "with_shared_preparation_seconds_saved_seconds_full_minus_fixed", "generation_fraction_full",
                     "generation_fraction_fixed", "generation_fraction_change_fixed_minus_full",
                     "public_optimizer_steps_full", "public_optimizer_steps_fixed", "public_optimizer_steps_change_fixed_minus_full"]
    client_fields = ["partition", "seed", "case_id", "method", "client", "width", "acc", "nmi", "ari",
                     "occupied_clusters", "largest_cluster_fraction", "cluster_counts"]
    memory_fields = ["partition", "seed", "case_id", "method", "process_peak_working_set_bytes",
                     "persistent_method_array_bytes", "final_head_digest"]
    _write_csv(output / "summary.csv", summary_rows, summary_fields)
    _write_csv(output / "paired_cost.csv", paired_rows, paired_fields)
    _write_csv(output / "quality_guardrails.csv", guardrails, quality_fields)
    _write_csv(output / "budget_effects.csv", budget_effects, budget_fields)
    _write_csv(output / "final_clients.csv", client_rows, client_fields)
    if profiles:
        _write_csv(output / "memory_summary.csv", memory_rows, memory_fields)
    else:
        (output / "memory_summary.csv").unlink(missing_ok=True)
    aggregate = _summary_stats(cases, paired_rows, guardrails, profiles)
    # Retain the prescribed compact inputs and complete metric curves, dropping bulky trace payloads.
    compact_cases = []
    for case in cases:
        compact_cases.append({k: v for k, v in case.items()
                              if k not in ("round_records", "identity", "identities")})
    payload = {"cases": compact_cases, "profiles": profiles, "paired_cost_summary": aggregate,
               "quality_guardrails": guardrails, "budget_effects": budget_effects}
    (output / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (output / "report.md").write_text(_markdown(cases, aggregate, guardrails, budget_effects, profiles), encoding="utf-8")
    return payload

