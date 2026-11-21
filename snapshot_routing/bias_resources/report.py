"""Summarize paired timing, memory and measurement gates."""

from collections import defaultdict
from statistics import median

from experiments.snapshot_certification_timing.design import require
from ..report import write_csv
from .worker import non_timing


def total(run, key):
    return sum(r[key] for r in run["rows"])


def mismatch_count(run):
    return sum(sum(row["mismatches"]) for row in run["rows"])


def timing_block_eligible(old, new):
    power = {state for run in (old, new) for state in run["power"] if state is not None}
    return len(power) < 2 and all((run["suspend_seconds"] or 0.) < 1. for run in (old, new))


def peak_over_input(run):
    peak, baseline = run["process_peak_bytes"], run["input_peak_bytes"]
    return None if None in (peak, baseline) else peak - baseline


def bytes_delta(old, new):
    return None if None in (old, new) else new - old


def build(out, preset, runs, numerical):
    grouped = defaultdict(dict)
    for run in runs:
        grouped[run["cell"]].setdefault(run["method"], []).append(run)
    cells, pairs, phases = [], [], []
    for cell, methods in grouped.items():
        old_runs, new_runs = methods["old"], methods["new"]
        repeats = len(old_runs)
        require(repeats == len(new_runs) == (3 if preset == "full" else 1), f"Incomplete pairs for {cell}")
        for method_runs in (old_runs, new_runs):
            require(all(non_timing(run) == non_timing(method_runs[0]) for run in method_runs),
                    f"Repetitions disagree on non-timing evidence: {cell} {method_runs[0]['method']}")
        old, new = old_runs[0], new_runs[0]
        require("diagnostic" in old and "diagnostic" in new, f"Missing replay diagnostics for {cell}")
        block_rows = []
        for a, b in zip(old_runs, new_runs, strict=True):
            require(a["repeat"] == b["repeat"], f"Mismatched repeat in {cell}")
            a_seconds, b_seconds = total(a, "seconds"), total(b, "seconds")
            row = dict(cell=cell, repeat=a["repeat"], old_seconds=a_seconds, new_seconds=b_seconds,
                       new_over_old=b_seconds / a_seconds, eligible=timing_block_eligible(a, b),
                       old_peak_bytes=a["process_peak_bytes"], new_peak_bytes=b["process_peak_bytes"],
                       peak_delta_bytes=bytes_delta(a["process_peak_bytes"], b["process_peak_bytes"]),
                       old_peak_over_input_bytes=peak_over_input(a), new_peak_over_input_bytes=peak_over_input(b))
            block_rows.append(row)
        pairs.extend(block_rows)
        for run in (old, new):
            for row in run["diagnostic"]:
                phases.append(dict(cell=cell, method=run["method"], round=row["round"],
                                   generation_seconds=row["seconds"], advance_seconds=row["advance_seconds"],
                                   candidate_seconds=row["candidate_seconds"], refresh_seconds=row["refresh_seconds"],
                                   other_seconds=row["other_seconds"], scoring_macs=row["scoring_macs"],
                                   up_bytes=row["traffic"].get("up_bytes", 0),
                                   down_bytes=row["traffic"].get("down_bytes", 0)))
        old_traffic, new_traffic = (r["diagnostic"][-1]["traffic"] for r in (old, new))
        peak_deltas = [row["peak_delta_bytes"] for row in block_rows if row["peak_delta_bytes"] is not None]
        cells.append(dict(
            cell=cell, **old["case"], repeats=repeats, eligible_pairs=sum(row["eligible"] for row in block_rows),
            median_new_over_old=median(row["new_over_old"] for row in block_rows),
            old_mismatches=mismatch_count(old), new_mismatches=mismatch_count(new),
            checked_edges_per_method=old["edge_comparisons"],
            old_endpoints=sum(sum(row["endpoints"]) for row in old["rows"]),
            new_endpoints=sum(sum(row["endpoints"]) for row in new["rows"]),
            old_scoring_macs=total(old, "scoring_macs"), new_scoring_macs=total(new, "scoring_macs"),
            old_cache_bytes=old["cache_bytes"], new_cache_bytes=new["cache_bytes"],
            median_peak_delta_bytes=median(peak_deltas) if peak_deltas else None,
            peak_verified=len(peak_deltas) == repeats,
            stable_peak_increase=len(peak_deltas) == repeats and all(delta > 0 for delta in peak_deltas),
            old_up_bytes=old_traffic["up_bytes"], new_up_bytes=new_traffic["up_bytes"],
            old_down_bytes=old_traffic["down_bytes"], new_down_bytes=new_traffic["down_bytes"],
            same_traffic_all_rounds=all(a["traffic"] == b["traffic"]
                                        for a, b in zip(old["diagnostic"], new["diagnostic"], strict=True)),
            old_traffic_rounds_equal_b=old["traffic_rounds_equal_b"],
            new_traffic_rounds_equal_b=new["traffic_rounds_equal_b"],
        ))
    write_csv(out / "cells.csv", cells)
    write_csv(out / "pairs.csv", pairs)
    write_csv(out / "phases.csv", phases)

    confirmation = [r for r in cells if r["public_size"] == 4096 and r["seed"] in (2022, 2023)]
    decisions = {}
    if preset == "full":
        for partition in ("iid", "dirichlet_0.1"):
            rows = [r for r in confirmation if r["partition"] == partition]
            require(len(rows) == 2, f"Missing confirmation seeds for {partition}")
            ratio = median(r["median_new_over_old"] for r in rows)
            checks = dict(
                eligibility=all(r["eligible_pairs"] == 3 for r in rows),
                timing=ratio <= 1. and all(r["median_new_over_old"] <= 1.02 for r in rows),
                relations=all(r["old_mismatches"] == r["new_mismatches"] == 0 for r in rows),
                scoring=all(r["new_scoring_macs"] <= r["old_scoring_macs"] for r in rows),
                cache=all(r["new_cache_bytes"] <= r["old_cache_bytes"] for r in rows),
                peak=all(r["peak_verified"] and not r["stable_peak_increase"] for r in rows),
                communication=all(r["same_traffic_all_rounds"] for r in rows),
            )
            decisions[partition] = dict(ratio=ratio, checks=checks, passed=all(checks.values()))
    resource_passed = all(d["passed"] for d in decisions.values()) if decisions else None
    other_mismatch_cells = [r["cell"] for r in cells if r["old_mismatches"] or r["new_mismatches"]]
    lines = [
        "# 旧 D 与偏置净变化 D 的资源对照", "",
        f"范围为 {preset}，共 {len(cells)} 个配置、{len(pairs)} 个计时配对。只回放关系生成。", "",
        f"第一项合成数值验收为 **{numerical['status']}**，独立于本次资源门槛。", "",
        "| 配置 | 新/旧生成耗时 | 旧 D 错边 | 新 D 错边 | 重打分 MACs 变化 | 持久缓存变化 B | 峰值工作集差 B（中位数） | 全轮通信一致 |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in cells:
        mac_change = 100. * (r["new_scoring_macs"] / r["old_scoring_macs"] - 1.)
        cache_change = r["new_cache_bytes"] - r["old_cache_bytes"]
        peak = r["median_peak_delta_bytes"]
        peak_text = "缺失" if peak is None else f"{peak:+,.0f}"
        lines.append(f"| {r['cell']} | {r['median_new_over_old']:.4f} | {r['old_mismatches']:,} | "
                     f"{r['new_mismatches']:,} | {mac_change:+.2f}% | {cache_change:+,} | "
                     f"{peak_text} | {'是' if r['same_traffic_all_rounds'] else '否'} |")
    lines.extend(["", "## M4096 确认判定", ""])
    if not decisions:
        lines.append("冒烟只验证运行流程。")
    for partition, decision in decisions.items():
        failures = [key for key, passed in decision["checks"].items() if not passed]
        lines.append(f"- {partition} 通过={decision['passed']}，比值={decision['ratio']:.4f}，"
                     f"未通过项={', '.join(failures) if failures else '无'}。")
    lines.extend([
        "",
        "耗时包含初始化和后续关系生成。逐边核验、图注册、协议回放和带探针分段计时在主计时之外。",
        "MACs 只核算线性打分，认证的实际耗时见 phases.csv。峰值工作集含已加载输入和进程运行库。",
        "采集到供电切换或休眠时保留原始配对，并让该配置的计时资格未通过。未知供电和休眠读数原样保留。",
        "通信数据来自原协议的内存回放，包含注册及双向消息字节。当前结果适用于冻结的教师快照。",
    ])
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dict(resource_passed=resource_passed, decisions=decisions, mismatch_cells=other_mismatch_cells)
