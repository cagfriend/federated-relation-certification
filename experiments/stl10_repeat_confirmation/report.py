"""Repeat-confirmation report: noise, seed-level pairing, C1/C2/C3 verdicts."""
import csv
import json
from pathlib import Path

from .design import summarize


def _csv(path, rows):
    if rows:
        with Path(path).open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def reports(output, runs, guardrails, *, fixture=False, preset='full'):
    output = Path(output)
    noise, seed_rows, verdicts = summarize(runs)
    _csv(output / 'noise.csv', noise)
    _csv(output / 'seed_pairs.csv', seed_rows)
    _csv(output / 'guardrail.csv', guardrails)
    payload = dict(verdicts=verdicts, seed_pairs=seed_rows, guardrail=guardrails,
                   fixture=fixture, preset=preset, runs=len(runs))
    (output / 'verdict.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    pct = lambda ratio: f'{(1 - ratio) * 100:.2f}%'  # noqa: E731
    mark = lambda ok: '✓' if ok else '✗'  # noqa: E731
    lines = ['# STL-10 固定 2 步重复计时确认报告', '']
    if fixture:
        lines += ['> 合成夹具 smoke：只验证实现与判定机械流程，不构成实验结论。', '']
    lines += ['本批次全部新跑，计时不与探索批次混合；轨迹经'
              + ('块内一致性核查（夹具无历史锚点）。' if fixture else '三重锚点与块内一致性核查。')
              + '主指标为完整头部耗时，先在 seed 内对 3 次重复取均值，再逐 seed 配对。', '',
              '## 逐划分判定', '',
              '| 划分 | D/B 中位比值（省时） | D/E 中位比值（省时） | 胜出 B | 胜出 E | C1 | C2 | C3 | 确认 |',
              '|---|---:|---:|---:|---:|:--:|:--:|:--:|:--:|']
    for part, v in verdicts.items():
        lines.append(f"| {part} | {v['median_ratio_DB']:.4f}（{pct(v['median_ratio_DB'])}） "
                     f"| {v['median_ratio_DE']:.4f}（{pct(v['median_ratio_DE'])}） "
                     f"| {v['wins_B']}/3 | {v['wins_E']}/3 | {mark(v['C1'])} | {mark(v['C2'])} | {mark(v['C3'])} "
                     f"| {mark(v['confirmed'])} |")
    lines += ['', '## 逐 seed（重复均值口径）', '',
              '| 划分 | seed | B 均值秒 | E 均值秒 | D 均值秒 | D/B 省时 | D/E 省时 | D/B 省秒 | D/E 省秒 | 逐重复D/B比值范围 | 逐重复D/E比值范围 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in seed_rows:
        lines.append(f"| {r['partition']} | {r['seed']} | {r['B_mean']:.3f} | {r['E_mean']:.3f} | {r['D_mean']:.3f} "
                     f"| {pct(r['ratio_DB'])} | {pct(r['ratio_DE'])} | {r['saved_DB']:.3f} | {r['saved_DE']:.3f} "
                     f"| {r['repeat_ratio_DB_min']:.4f}–{r['repeat_ratio_DB_max']:.4f} "
                     f"| {r['repeat_ratio_DE_min']:.4f}–{r['repeat_ratio_DE_max']:.4f} |")
    worst = {}
    for n in noise:
        key = n['method']
        if key not in worst or n['relative_range'] > worst[key]:
            worst[key] = n['relative_range']
    lines += ['', '## 重复噪声（描述）', '',
              '逐（块、方法）明细见 noise.csv。各方法 3 次重复相对极差的最大值：'
              + '；'.join(f"{m} {worst[m] * 100:.2f}%" for m in sorted(worst)) + '。', '',
              '## 退化护栏（B 轨迹）', '',
              '| 划分 | seed | 最终ACC | S1 | S2 | Q1 | Q2 | 通过 |', '|---|---:|---:|:--:|:--:|:--:|:--:|:--:|']
    for g in guardrails:
        lines.append(f"| {g['partition']} | {g['seed']} | {g['final_acc']:.4f} "
                     f"| {mark(g['S1'])} | {mark(g['S2'])} | {mark(g['Q1'])} | {mark(g['Q2'])} | {mark(g['passed'])} |")
    lines += ['', '本报告不作并行时延或普适加速声明；质量仅作护栏。', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    return verdicts
