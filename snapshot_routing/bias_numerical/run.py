"""Run the paired old-D/new-D audit on fixed binary64 fixtures."""

import argparse
from pathlib import Path

from ..numerical_check.run import metadata, snapshot_archive

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import ROOT, environment, require, seal, sha, write
from ..report import write_csv
from .audit import CHANGES, DIAGNOSTICS, FACTORIES, audit
from .design import comparison_fixtures


PACKAGE = Path(__file__).resolve().parent
EXPECTED_ORIGINAL_FAILURES = {
    "prefix_p54_n32", "prefix_p54_n256", "prefix_p60_n1024",
}
COUNTS = ("b_vs_exact_labels", "b_vs_exact_edges", *CHANGES)


def summarize(spec, rows):
    summary = dict(spec)
    for field in COUNTS:
        summary[field] = sum(row[field] or 0 for row in rows)
    summary["paired_rounds"] = sum(row["fixed"] is not None for row in rows)
    summary["paired_edge_positions"] = summary["paired_rounds"] * spec["edges"]
    for name in FACTORIES:
        for field in (*DIAGNOSTICS, "forward_endpoints", "exception"):
            key = f"{name}_{field}"
            summary[key] = sum(row[key] or 0 for row in rows)
    return summary


def gate(summary):
    bias_cases = [row for row in summary if row["family"] in ("long_prefix", "heldout_bias_prefix")]
    expected = [row for row in bias_cases
                if row["name"] in EXPECTED_ORIGINAL_FAILURES or row["family"] == "heldout_bias_prefix"]
    return {
        "incomplete": [row["name"] for row in summary if row["paired_rounds"] != row["rounds"]],
        "baseline_witness_not_reproduced": [row["name"] for row in expected if not row["old_edges_vs_b"]],
        "bias_prefix_still_differs": [row["name"] for row in bias_cases if row["new_edges_vs_b"]],
        "new_differences": [row["name"] for row in summary if row["introduced"]],
    }


def report(out, preset, summary, rounds):
    write_csv(out / "cases.csv", summary)
    write_csv(out / "rounds.csv", rounds)
    failures = gate(summary)
    passed = not any(failures.values())
    label = "通过" if passed else "未通过"
    scope = "完整矩阵" if preset == "full" else "冒烟子集"
    lines = [
        "# 偏置净变化数值对照", "",
        f"范围为{scope}，判定为**{label}**。共 {len(summary)} 个实例。",
        f"共同核对 {sum(row['paired_edge_positions'] for row in summary):,} 个边位置（每个位置比较新旧 D）。",
        "",
        "| 实例 | B 对有理数错边 | 旧 D 对 B | 新 D 对 B | 已修复 | 残留 | 新引入 | 配对轮次 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary:
        lines.append(
            f"| {row['name']} | {row['b_vs_exact_edges']} | {row['old_edges_vs_b']} | "
            f"{row['new_edges_vs_b']} | {row['fixed']} | {row['remaining']} | {row['introduced']} | "
            f"{row['paired_rounds']}/{row['rounds']} |"
        )
    lines.extend(["", "## 判定细目", ""])
    for key, names in failures.items():
        lines.append(f"- `{key}`：{', '.join(names) if names else '无'}")
    lines.extend([
        "",
        "同一轮、同一边编号用于判定已修复、残留与新引入。方法异常后的轮次缺失计数，"
        "完整性未通过。权重前缀及大数相消的残留单列。",
        "CSV 含候选排除、回退标签分歧和打分端点数。JSON 与 NPZ 保留第一处异常的可复现证据。",
    ])
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return passed, failures


def execute(out, preset):
    cases = comparison_fixtures(preset)
    expected_count = 21 if preset == "full" else 7
    require(len(cases) == len({case.name for case in cases}) == expected_count,
            "The fixture matrix changed")
    require(not out.exists() or (out.is_dir() and not any(out.iterdir())),
            "Use an empty output directory")
    sources = [*sorted(PACKAGE.glob("*.py")), *sorted((PACKAGE.parent / "numerical_check").glob("*.py")),
               PACKAGE.parent / "report.py",
               ROOT / "experiments/public_scaling/certification.py"]
    manifest = out / "manifest.json"
    specs = [metadata(case) for case in cases]
    write(manifest, dict(preset=preset, fixtures=specs, environment=environment(),
                         sources={path.relative_to(ROOT).as_posix(): sha(path) for path in sources}))
    identity = sha(manifest)
    summary, rounds, hashes = [], [], {}
    for case, spec in zip(cases, specs, strict=True):
        print(f"{case.name}: {spec['rounds']} snapshots", flush=True)
        observations, first_events, witnesses = audit(case)
        if first_events:
            path = out / "witnesses" / f"{case.name}.npz"
            digest = snapshot_archive(path, case)
            witness = dict(path=path.relative_to(out).as_posix(), sha256=digest)
        else:
            witness = None
        path = out / "cases" / f"{case.name}.json"
        seal(path, dict(manifest=identity, case=spec, rounds=observations, first_events=first_events,
                        first_event_snapshots=witnesses, input_witness=witness))
        hashes[path.relative_to(out).as_posix()] = sha(path)
        summary.append(summarize(spec, observations))
        rounds.extend(dict(case=case.name, family=case.family, **row) for row in observations)
    passed, failures = report(out, preset, summary, rounds)
    seal(out / "completed.json", dict(manifest=identity, preset=preset, passed=passed,
                                     failures=failures, records=hashes))
    print(f"Finished ({'pass' if passed else 'fail'}): {out / 'report.md'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preset", choices=("full", "smoke"), default="full")
    parser.add_argument("--output", type=Path)
    options = parser.parse_args()
    out = (options.output or ROOT / "outputs" / f"snapshot_routing_bias_numerical_{options.preset}").resolve()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(out, options.preset)


if __name__ == "__main__":
    main()
