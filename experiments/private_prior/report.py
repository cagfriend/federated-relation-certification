"""Quality-only paired reports. Timings are retained in raw records."""
import csv
import json
from pathlib import Path

import numpy as np


def measurements(record, smoke=False):
    rounds = record["config"]["rounds"]
    first = 1 if smoke else 161
    diagnostics = record["diagnostic_records"]
    rates = [[r["clients"][c]["positive_relation_fraction_T1"] for r in diagnostics if r["round"] >= first]
             for c in (0, 3)]
    checkpoints = record["metrics"] if smoke else [m for m in record["metrics"] if m["round"] in (160, 180, 200)]
    expected = list(range(1, rounds + 1)) if smoke else [160, 180, 200]
    healthy = [m["round"] for m in checkpoints] == expected and all(
        [c["client"] for c in m["clients"]] == list(range(6)) and all(
            c["occupied_clusters"] > 1 and c["largest_cluster_fraction"] < .99 for c in m["clients"])
        for m in checkpoints)
    return dict(c0_late=float(np.mean(rates[0])), c3_late=float(np.mean(rates[1])),
                small_late=float(np.mean(rates)), healthy=healthy,
                acc=record["metrics"][-1]["mean"]["acc"],
                early95=[sum(d["clients"][c]["positive_relation_fraction_T1"] >= .95
                             for d in diagnostics[:40]) for c in (0, 3)])


def report(out, entries, smoke=False):
    rows, curves, quality = [], [], []
    for case, current, baseline in entries:
        new, old = measurements(current, smoke), measurements(baseline, smoke)
        row = dict(**case, baseline_small_late=old["small_late"], corrected_small_late=new["small_late"],
                   improvement_pp=100*(old["small_late"]-new["small_late"]),
                   c0_improvement_pp=100*(old["c0_late"]-new["c0_late"]),
                   c3_improvement_pp=100*(old["c3_late"]-new["c3_late"]),
                   healthy=new["healthy"], acc_change_pp=100*(new["acc"]-old["acc"]),
                   baseline_c0_early95=old["early95"][0], corrected_c0_early95=new["early95"][0],
                   baseline_c3_early95=old["early95"][1], corrected_c3_early95=new["early95"][1])
        row["passed"] = (row["improvement_pp"] >= 10 and row["c0_improvement_pp"] > 0
                         and row["c3_improvement_pp"] > 0 and row["healthy"] and row["acc_change_pp"] >= -1)
        rows.append(row)
        for branch, record in (("baseline", baseline), ("prior", current)):
            for d in record["diagnostic_records"]:
                for c in d["clients"]:
                    curves.append(dict(**case, branch=branch, round=d["round"], client=c["client"],
                                       same_edge=c["positive_relation_fraction_T1"],
                                       private_fit=c["T2"]["private"]["fixed_pseudo_fit"],
                                       t0_public_max=c["T0"]["public"]["largest_cluster_fraction"],
                                       t1_public_max=c["T1"]["public"]["largest_cluster_fraction"],
                                       t2_public_max=c["T2"]["public"]["largest_cluster_fraction"]))
            for m in record["metrics"]:
                for c in m["clients"]:
                    quality.append(dict(**case, branch=branch, round=m["round"], **{
                        k: c[k] for k in ("client", "acc", "nmi", "ari", "occupied_clusters", "largest_cluster_fraction")}))
    for name, data in (("paired.csv", rows), ("curves.csv", curves), ("quality.csv", quality)):
        with (Path(out)/name).open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
    text = ["# 私有伪簇频数校正", "",
            "合成 smoke 验证，不构成正式证据。" if smoke else "四条既有环境上的探索性协作干预。统计单位为 seed 配对轨迹。",
            "", "| 划分 | seed | 末40轮小端同簇边下降/百分点 | ACC变化/百分点 | 通过 |",
            "|---|---:|---:|---:|---|"]
    text += [f'| {r["partition"]} | {r["seed"]} | {r["improvement_pp"]:.2f} | {r["acc_change_pp"]:.2f} | {r["passed"]} |' for r in rows]
    text += ["", "## 末轮逐客户端质量", "",
             "| 划分 | seed | 分支 | 客户端 | ACC | NMI | ARI | 占用簇 | 最大簇 |",
             "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for q in quality:
        if q["round"] == entries[0][1]["config"]["rounds"]:
            text.append(f'| {q["partition"]} | {q["seed"]} | {q["branch"]} | {q["client"]} | '
                        f'{q["acc"]:.4f} | {q["nmi"]:.4f} | {q["ari"]:.4f} | '
                        f'{q["occupied_clusters"]} | {q["largest_cluster_fraction"]:.4f} |')
    text += ["", "四条全部通过，才进入同一学习目标下的 B/E/D 计算比较。" ,
             "检查原始逐端结果及早期集中轮数。报告只作质量诊断，耗时字段保留在原始记录中。"]
    (Path(out)/"report.md").write_text("\n".join(text)+"\n", encoding="utf-8")
    (Path(out)/"decision.json").write_text(json.dumps(dict(smoke=smoke, all_passed=all(r["passed"] for r in rows),
                                                          cases=rows), indent=2)+"\n", encoding="utf-8")
