"""Report generation for the public-pool scaling experiment.

This module intentionally has no imports from the legacy experiment package.
It consumes the JSON-like dictionaries returned by ``engine.run_seed``.
"""

import csv
import json
import math
import statistics
from pathlib import Path


TIME_FIELDS = (
    "generation_seconds",
    "training_pipeline_seconds",
    "with_shared_preparation_seconds",
)
METRICS = ("nmi", "ari", "acc")
METHOD_ORDER = ("B", "E", "D")
SUMMARY_FIELDS = (
    "training_pipeline_seconds",
    "with_shared_preparation_seconds",
    "private_seconds",
    "generation_seconds",
    "exchange_seconds",
    "public_seconds",
    "teacher_recompute_fraction_after_bootstrap",
    "student_forward_endpoints",
    "private_optimizer_steps",
    "public_optimizer_steps",
    "persistent_method_array_bytes",
)
MEMORY_FIELDS = (
    "persistent_method_array_bytes",
    "tracemalloc_peak_bytes",
    "process_peak_working_set_bytes",
)


def _json_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _case_id(case):
    if case.get("case_id") is not None:
        return str(case["case_id"])
    config = case.get("config", {})
    if config.get("samples") is not None and config.get("degree") is not None:
        return f"m{config['samples']}_d{config['degree']}"
    return "unspecified"


def _sort_case_id(value):
    return value


def _flatten_cases(cases):
    flattened = []
    for case in cases:
        config = case.get("config") or {}
        case_id = _case_id(case)
        for method, summary in (case.get("summary") or {}).items():
            metrics = (summary.get("final_metrics") or {}).get("mean") or {}
            traffic = summary.get("traffic") or {}
            row = {
                "case_id": case_id,
                "seed": case.get("seed"),
                "method": method,
                "dataset": case.get("dataset"),
                "samples": config.get("samples"),
                "degree": config.get("degree"),
                "public_pool": config.get("public_pool"),
                "configured_rounds": config.get("rounds"),
            }
            row.update({field: summary.get(field) for field in SUMMARY_FIELDS})
            row["communication_bytes"] = traffic.get("total_bytes", 0)
            row.update({metric: metrics.get(metric) for metric in METRICS})
            row["clients"] = _json_value((summary.get("final_metrics") or {}).get("clients", []))
            flattened.append(row)
    return flattened


def _paired_groups(cases):
    groups = {}
    for case in cases:
        case_id = _case_id(case)
        seed = case.get("seed")
        if seed in groups.setdefault(case_id, {}):
            raise ValueError('Duplicate case_id/seed would corrupt pairing')
        groups[case_id][seed] = case

    result = {}
    for case_id in sorted(groups, key=_sort_case_id):
        seeds = groups[case_id]
        refs = {}
        for reference in ("B", "E"):
            reference_result = {}
            for field in TIME_FIELDS:
                pairs = []
                unpaired = []
                for seed in sorted(seeds, key=lambda x: (x is None, str(x))):
                    summaries = seeds[seed].get("summary") or {}
                    d = summaries.get("D")
                    ref = summaries.get(reference)
                    if (not d or not ref or not _numeric(d.get(field)) or
                            not _numeric(ref.get(field)) or ref[field] == 0):
                        unpaired.append(seed)
                        continue
                    ratio = d[field] / ref[field]
                    pairs.append({
                        "seed": seed,
                        "D_seconds": d[field],
                        "reference_seconds": ref[field],
                        "ratio_D_over_reference": ratio,
                        "seconds_saved_reference_minus_D": ref[field] - d[field],
                        "D_teacher_recompute_fraction_after_bootstrap": d.get(
                            "teacher_recompute_fraction_after_bootstrap"),
                        "reference_teacher_recompute_fraction_after_bootstrap": ref.get(
                            "teacher_recompute_fraction_after_bootstrap"),
                    })
                ratios = [pair["ratio_D_over_reference"] for pair in pairs]
                savings = [pair["seconds_saved_reference_minus_D"] for pair in pairs]
                reference_result[field] = {
                    "paired_count": len(pairs),
                    "unpaired_seeds": unpaired,
                    "wins_D_faster": sum(value < 1 for value in ratios),
                    "median_ratio_D_over_reference": statistics.median(ratios) if ratios else None,
                    "ratio_range": {"min": min(ratios), "max": max(ratios)} if ratios else None,
                    "median_seconds_saved": statistics.median(savings) if savings else None,
                    "seconds_saved_range": {"min": min(savings), "max": max(savings)} if savings else None,
                    "raw_pairs": pairs,
                }
            recompute_pairs = [
                {"seed": seed,
                 "D": (seeds[seed].get("summary") or {}).get("D", {}).get(
                     "teacher_recompute_fraction_after_bootstrap"),
                 reference: (seeds[seed].get("summary") or {}).get(reference, {}).get(
                     "teacher_recompute_fraction_after_bootstrap")}
                for seed in sorted(seeds, key=lambda x: (x is None, str(x)))
                if "D" in (seeds[seed].get("summary") or {}) and
                reference in (seeds[seed].get("summary") or {})
            ]
            recompute_summary = {}
            for method in ("D", reference):
                values = [pair[method] for pair in recompute_pairs if _numeric(pair.get(method))]
                recompute_summary[method] = {
                    "count": len(values),
                    "median": statistics.median(values) if values else None,
                    "range": {"min": min(values), "max": max(values)} if values else None,
                    "wins_lower_than_other_method": sum(
                        _numeric(pair.get(method)) and _numeric(pair.get(reference if method == "D" else "D"))
                        and pair[method] < pair[reference if method == "D" else "D"]
                        for pair in recompute_pairs),
                }
            reference_result["recomputation"] = {
                "summary": recompute_summary,
                "raw_pairs": recompute_pairs,
            }
            refs[f"D_over_{reference}"] = reference_result
        result[case_id] = {
            "case_id": case_id,
            "config": next((case.get("config", {}) for case in seeds.values()), {}),
            "seed_count": len(seeds),
            "seeds": sorted(seeds, key=lambda x: (x is None, str(x))),
            "paired": refs,
        }
    return result


def _metric_consistency(cases):
    checks = []
    for case in cases:
        summaries = case.get("summary") or {}
        available = [method for method in METHOD_ORDER if method in summaries]
        metrics = {method: (summaries[method].get("final_metrics") or {}).get("mean") or {}
                   for method in available}
        consistent = True
        for metric in METRICS:
            values = [metrics[m].get(metric) for m in available]
            if len(values) >= 2 and (any(not _numeric(v) for v in values) or
                                    any(v != values[0] for v in values[1:])):
                consistent = False
        checks.append({"case_id": _case_id(case), "seed": case.get("seed"),
                       "methods_present": available, "consistent": consistent,
                       "mean_metrics": metrics})
    return checks


def _memory_rows(memory):
    grouped = {}
    for item in memory:
        case_id = str(item.get("case_id", "unspecified"))
        method = item.get("method", "unspecified")
        grouped.setdefault((case_id, method), []).append(item)
    rows = []
    for (case_id, method), items in sorted(grouped.items()):
        row = {"case_id": case_id, "method": method, "profiles": len(items)}
        for field in MEMORY_FIELDS:
            vals = [item.get(field) for item in items if _numeric(item.get(field))]
            row[field + "_median"] = statistics.median(vals) if vals else ""
            row[field + "_min"] = min(vals) if vals else ""
            row[field + "_max"] = max(vals) if vals else ""
        row["rounds"] = _json_value(sorted({item.get("rounds") for item in items}, key=str))
        row["seeds"] = _json_value(sorted({item.get("seed") for item in items}, key=str))
        rows.append(row)
    return rows


def _write_csv(path, rows, fieldnames):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _build_markdown(cases, rows, paired, memory_rows, checks, expected_seeds):
    case_map = {}
    for case in cases:
        case_map.setdefault(_case_id(case), []).append(case)
    lines = [
        "# Fashion-MNIST 公共池规模实验",
        "",
        "本报告按 `case_id`（样本数 M 与度数 degree 的组合）分别配对；不同 M 或 degree 的轨迹不要求相同，也不会跨配置合并配对。",
        "",
        "## 配置完成情况",
        "",
        "| case_id | M | degree | public_pool | 完成种子数 | 已完成 seeds | 状态 |",
        "|:---|---:|---:|---:|---:|:---|:---|",
    ]
    for case_id in sorted(case_map):
        members = case_map[case_id]
        config = members[0].get("config") or {}
        seed_values = sorted((c.get("seed") for c in members), key=lambda x: (x is None, str(x)))
        complete = (set(seed_values) == set(expected_seeds) and
                    all({"B", "E", "D"}.issubset(set((c.get("summary") or {}).keys())) for c in members))
        lines.append(f"| {case_id} | {config.get('samples', '')} | {config.get('degree', '')} | {config.get('public_pool', '')} | {len(members)} | {_json_value(seed_values)} | {'complete' if complete else 'partial'} |")
    lines += [
        "",
        f"未达到记录计划中预定 seeds={expected_seeds} 的组标为 partial。标准 full 目标为 M=4096/8192/16384、degree=1，Fashion-MNIST 固定私有集 43,616 与公共池 16,384；degree=4/8 属于可选扩展配置。smoke 为缩小的路径验证配置，不作正式性能结论。",
        "",
        "## 指标与耗时",
        "",
        "| case_id | seed | 方法 | 训练流程秒 | 含共享准备秒 | generation 秒 | 私有秒 | 公共秒 | NMI | ARI | ACC | 私有步数 | 公共步数 | 通信字节 |",
        "|:---|---:|:---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        def fmt(value, digits=4):
            return f"{value:.{digits}f}" if _numeric(value) else ""
        lines.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            row["case_id"], row["seed"], row["method"], fmt(row.get("training_pipeline_seconds"), 3),
            fmt(row.get("with_shared_preparation_seconds"), 3), fmt(row.get("generation_seconds"), 3),
            fmt(row.get("private_seconds"), 3), fmt(row.get("public_seconds"), 3),
            fmt(row.get("nmi")), fmt(row.get("ari")), fmt(row.get("acc")),
            row.get("private_optimizer_steps", ""), row.get("public_optimizer_steps", ""),
            row.get("communication_bytes", "")))
    lines += [
        "",
        "在每一个配置内部，B/E/D 应保持相同的学习质量指标；跨 M 或 degree 的学习轨迹不要求相同。自动检查结果：",
        "",
    ]
    if checks:
        for check in checks:
            lines.append(f"- `{check['case_id']}` seed {check['seed']}: {'通过' if check['consistent'] else '不一致/缺失'}（可用方法：{', '.join(check['methods_present'])}）。")
    else:
        lines.append("- 没有可检查的 case。")
    lines += [
        "",
        "## 配对比较",
        "",
        "以下均先在同一 case、同一 seed 内计算 D/参照及参照耗时减 D 耗时，再按该配置汇总。胜出表示 D 的对应耗时更低。raw pairs 与重算比例位于 `paired_summary.json`。",
        "",
        "| case_id | 对照 | 耗时项 | pairs | wins | D/参照中位数 [范围] | 中位省时秒 [范围] |",
        "|:---|:---|:---|---:|---:|---:|---:|",
    ]
    for case_id, group in paired.items():
        for comparator, measurements in group["paired"].items():
            for field, stat in measurements.items():
                if field == "recomputation":
                    continue
                ratio = stat["median_ratio_D_over_reference"]
                rr = stat["ratio_range"]
                saving = stat["median_seconds_saved"]
                sr = stat["seconds_saved_range"]
                ratio_txt = "" if ratio is None else f"{ratio:.4f} [{rr['min']:.4f}, {rr['max']:.4f}]"
                saving_txt = "" if saving is None else f"{saving:.4f} [{sr['min']:.4f}, {sr['max']:.4f}]"
                lines.append(f"| {case_id} | {comparator} | {field} | {stat['paired_count']} | {stat['wins_D_faster']} | {ratio_txt} | {saving_txt} |")
    lines += [
        "",
        "## 成本口径与实验边界",
        "",
        "C0 每个 seed 一次准备同一私有数据和整个最大公共池（含测试特征）；缓存复用不再次支付它。C0+加载+T 是共用最大公共池准备策略下的成本核算，小 M 也承担完整池 C0，并非每个 M 各自最低独立准备成本；不按方法或配置数均摊。主要比较 T，C0+T 作为该准备策略的辅助口径。学生更新预算会随 M 与 degree 改变，不能把不同配置耗时差异解释为固定学生预算下的算法加速。",
        "",
        "这些结果是本地串行模拟与内存消息成本，不代表真实网络延迟、真实分布式行为或能耗。内存回放数据与性能计时分开记录。",
        "",
        "## 内存",
        "",
        "`memory_summary.csv` 按 case_id 与 method 分组，列出 profiles 数及持久方法数组、tracemalloc 与进程工作集峰值的中位数/范围。",
        "",
        "[逐 seed 方法汇总](summary.csv) · [配置内配对统计](paired_summary.json) · [内存汇总](memory_summary.csv)",
        "",
    ]
    if memory_rows:
        lines.insert(-2, f"内存档案数：{sum(row['profiles'] for row in memory_rows)}。进程峰值包含运行环境和评价，不等于方法独占状态。")
    else:
        lines.insert(-2, "未提供隔离内存回放记录；内存字段未测。")
    return "\n".join(lines)


def write_reports(output, cases, memory):
    """Write summary.csv, paired_summary.json, report.md and memory_summary.csv."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cases = list(cases or [])
    memory = list(memory or [])

    rows = _flatten_cases(cases)
    summary_fields = [
        "case_id", "seed", "method", "dataset", "samples", "degree", "public_pool", "configured_rounds",
        *SUMMARY_FIELDS, "communication_bytes", *METRICS, "clients",
    ]
    _write_csv(output / "summary.csv", rows, summary_fields)

    paired = _paired_groups(cases)
    paired_payload = {
        "seed_count": len({c.get('seed') for c in cases}),
        "completed_case_seed_count": len(cases),
        "case_count": len(paired),
        "pairing_policy": "strictly within case_id and shared seed; never combine different sample counts or graph degrees",
        "paired": paired,
        "metric_consistency_checks": _metric_consistency(cases),
    }
    with (output / "paired_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(paired_payload, handle, ensure_ascii=False, indent=2, allow_nan=False)

    memory_rows = _memory_rows(memory)
    memory_fields = ["case_id", "method", "profiles", *[f"{field}_{suffix}" for field in MEMORY_FIELDS
                     for suffix in ("median", "min", "max")], "rounds", "seeds"]
    _write_csv(output / "memory_summary.csv", memory_rows, memory_fields)
    env_path = output / 'environment.json'
    expected = json.loads(env_path.read_text(encoding='utf-8'))['seeds'] if env_path.exists() else [404, 505, 606]
    (output / "report.md").write_text(_build_markdown(cases, rows, paired, memory_rows,
                                                       paired_payload["metric_consistency_checks"], expected),
                                       encoding="utf-8")
