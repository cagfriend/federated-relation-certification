"""Mechanical verdict report for the STL-10 long-horizon validation."""
import json
from pathlib import Path

from .design import STEPS, evaluate_trajectory, select_tier


def collect(runs):
    """Return (per-trajectory rows, passed-by-steps, selected tier)."""
    rows = []
    for meta, record in runs:
        verdict = evaluate_trajectory(record)
        final = record['checkpoints'][-1]
        rows.append(dict(seed=meta['seed'], partition=meta['partition'], steps=meta['steps'],
                         final_acc=final['mean']['acc'], final_nmi=final['mean']['nmi'],
                         final_single_clients=final['single_cluster_clients'],
                         final_mean_largest=final['mean_largest_cluster_fraction'],
                         final_max_client_largest=max(c['largest_cluster_fraction'] for c in final['clients']),
                         final_edge_fraction=record['round_records'][-1]['positive_relation_fraction'],
                         events=len(record['events']), **verdict))
    by_steps = {s: [r['passed'] for r in rows if r['steps'] == s] for s in STEPS}
    return rows, by_steps, select_tier(by_steps)


def reports(out, runs, *, fixture=False, preset='full'):
    out = Path(out)
    rows, by_steps, selected = collect(runs)
    verdict = dict(fixture=fixture, preset=preset, trajectories=rows,
                   tier_validated={str(s): bool(v) and all(v) for s, v in by_steps.items()},
                   selected_steps=selected)
    (out / 'verdict.json').write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# STL-10 公共步数候选长程验证报告', '']
    if fixture:
        lines += ['> 本报告来自合成夹具 smoke：只验证实现与判定机械流程，'
                  '其中通过/未通过不构成任何实验结论。', '']
    lines += ['判定按冻结协议机械执行：阈值是运行前预先规定的操作标准，'
              '不是理论上的健康聚类界限，也不是经过校准的统计阈值。'
              '通过只能说明对应档位的这 4 条长程轨迹满足约定标准，'
              '不能保证其他种子或分布均不塌缩。', '',
              '|seed|划分|公共步数|最终ACC|最终NMI|单簇客户端|最大簇均值|单客户端最大簇|教师边比例|S1|S2|Q1|Q2|通过|事件数|',
              '|---:|---|---:|---:|---:|---:|---:|---:|---:|:--:|:--:|:--:|:--:|:--:|---:|']
    for r in rows:
        mark = lambda ok: '✓' if ok else '✗'  # noqa: E731
        lines.append(f"|{r['seed']}|{r['partition']}|{r['steps']}|{r['final_acc']:.4f}|{r['final_nmi']:.4f}"
                     f"|{r['final_single_clients']}|{r['final_mean_largest']:.4f}|{r['final_max_client_largest']:.4f}"
                     f"|{r['final_edge_fraction']:.4f}|{mark(r['S1'])}|{mark(r['S2'])}|{mark(r['Q1'])}|{mark(r['Q2'])}"
                     f"|{mark(r['passed'])}|{r['events']}|")
    lines += ['', '## 档位判定', '']
    for s in STEPS:
        state = '获得完整验证' if by_steps[s] and all(by_steps[s]) else '未获得完整验证'
        lines.append(f"- 公共 {s} 步：{state}（{sum(by_steps[s])}/{len(by_steps[s])} 条轨迹通过）")
    lines += ['', '## 选档结果（冻结规则）', '']
    if selected is not None:
        lines.append(f'选定公共 **{selected} 步**：该档位 4 条轨迹全部通过'
                     + ('（2 步优先，理由仅为保留更多公共训练预算）。' if selected == 2 else '（2 步未获完整验证）。'))
    else:
        lines.append('两档均未获得完整验证 → **回到诊断**，不在 STL-10 上恢复 B/E/D 计算比较。')
    lines += ['', '计时仅描述性记录（步数不同则总工作量不同），本报告不作任何省时比较。', '']
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    return verdict
