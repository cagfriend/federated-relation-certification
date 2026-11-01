"""Paired compute report for the STL-10 step-2 B/E/D comparison."""
import csv
import json
import statistics as st
from pathlib import Path

from .design import METHODS, guardrail


def _csv(path, rows):
    if rows:
        with Path(path).open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)


def aggregate(runs):
    rows = []
    for r in runs:
        s = r['summary'][r['method']]
        fm = s['final_metrics']
        rows.append(dict(seed=r['seed'], partition=r['partition'], case_id=r['case_id'], method=r['method'],
                         head_pipeline_seconds=s['head_pipeline_seconds'], generation_seconds=s['generation_seconds'],
                         private_seconds=s['private_seconds'], public_seconds=s['public_seconds'],
                         with_shared_preparation_seconds=s['with_shared_preparation_seconds'],
                         generation_fraction=s.get('generation_fraction'),
                         teacher_recompute_fraction=s.get('teacher_recompute_fraction'),
                         student_forward_endpoints=s['student_forward_endpoints'],
                         private_forward_endpoints=s['private_forward_endpoints'],
                         traffic_total_bytes=s.get('traffic', {}).get('total_bytes'),
                         process_peak_bytes=r.get('process_peak_bytes'),
                         persistent_method_array_bytes=s['persistent_method_array_bytes'],
                         final_acc=fm['mean']['acc'], final_nmi=fm['mean']['nmi'], final_ari=fm['mean']['ari']))
    groups = {}
    for x in rows:
        groups.setdefault((x['partition'], x['seed']), {})[x['method']] = x
    paired = []
    for (part, seed), ms in sorted(groups.items()):
        if not all(m in ms for m in METHODS):
            continue
        for other in ('B', 'E'):
            d, b = ms['D'], ms[other]
            paired.append(dict(partition=part, seed=seed, comparison=f'D/{other}',
                               head_ratio=d['head_pipeline_seconds'] / b['head_pipeline_seconds'],
                               saved_seconds=b['head_pipeline_seconds'] - d['head_pipeline_seconds'],
                               generation_ratio=d['generation_seconds'] / b['generation_seconds'] if b['generation_seconds'] else None,
                               generation_saved_seconds=b['generation_seconds'] - d['generation_seconds'],
                               with_preparation_ratio=d['with_shared_preparation_seconds'] / b['with_shared_preparation_seconds'],
                               with_preparation_saved_seconds=b['with_shared_preparation_seconds'] - d['with_shared_preparation_seconds'],
                               D_acc=d['final_acc'], reference_acc=b['final_acc']))
    summary = []
    for key in sorted({(x['partition'], x['comparison']) for x in paired}):
        g = [x for x in paired if (x['partition'], x['comparison']) == key]
        v = [x['head_ratio'] for x in g]
        summary.append(dict(partition=key[0], comparison=key[1], n_seeds=len(g),
                            median_head_ratio=st.median(v), min_head_ratio=min(v), max_head_ratio=max(v),
                            head_wins=sum(z < 1 for z in v),
                            median_saved_seconds=st.median(x['saved_seconds'] for x in g),
                            median_generation_ratio=st.median(x['generation_ratio'] for x in g),
                            median_with_preparation_ratio=st.median(x['with_preparation_ratio'] for x in g),
                            median_with_preparation_saved_seconds=st.median(x['with_preparation_saved_seconds'] for x in g)))
    return rows, paired, summary


def guardrail_rows(runs):
    out = []
    for r in runs:
        if r['method'] != 'B':
            continue
        verdict = guardrail(r)
        final = r['metrics'][-1]
        out.append(dict(partition=r['partition'], seed=r['seed'],
                        final_acc=final['mean']['acc'], final_nmi=final['mean']['nmi'],
                        final_single_clients=sum(c['occupied_clusters'] == 1 for c in final['clients']),
                        final_mean_largest=float(sum(c['largest_cluster_fraction'] for c in final['clients']) / len(final['clients'])),
                        final_max_client_largest=max(c['largest_cluster_fraction'] for c in final['clients']),
                        final_edge_fraction=r['round_records'][-1]['positive_relation_fraction'],
                        **verdict))
    return sorted(out, key=lambda x: (x['partition'], x['seed']))


def reports(output, runs, fixture, preset):
    output = Path(output)
    rows, paired, summary = aggregate(runs)
    guards = guardrail_rows(runs)
    _csv(output / 'runs.csv', rows)
    _csv(output / 'paired_cost.csv', paired)
    _csv(output / 'paired_summary.csv', summary)
    _csv(output / 'guardrail.csv', guards)
    (output / 'summary.json').write_text(json.dumps(
        dict(paired_summary=summary, guardrail=guards, completed_runs=len(runs),
             dataset='STL-10 fixture' if fixture else 'STL-10',
             formal_independent_confirmation=False,
             note='One run per method; exploratory timing within this batch only.'), indent=2), encoding='utf-8')
    pct = lambda ratio: f'{(1 - ratio) * 100:.2f}%'  # noqa: E731
    lines = ['# STL-10 固定 2 步 B/E/D 计算对照报告', '',
             f"数据：**{'合成 STL-10 夹具（smoke）' if fixture else '官方 STL-10'}**；运行 {len(runs)} 条；preset：{preset}。", '',
             '每方法每配置只跑一次，计时只在本批次内比较（B 为本轮重跑，旧长程 B 只作轨迹锚点）。'
             '本轮为探索性迁移对照，不是独立性能确认；小幅收益是否排除机器噪声留待后续技术重复。', '',
             '## 完整头部耗时（配对）', '',
             '| 划分 | 比较 | seed 数 | 中位省时 | 比值范围 | 胜出 | 中位省秒 | 生成中位省时 |',
             '|---|---|---:|---:|---:|---:|---:|---:|']
    for x in summary:
        lines.append(f"| {x['partition']} | {x['comparison']} | {x['n_seeds']} | {pct(x['median_head_ratio'])} "
                     f"| {x['min_head_ratio']:.4f}–{x['max_head_ratio']:.4f} | {x['head_wins']}/{x['n_seeds']} "
                     f"| {x['median_saved_seconds']:.3f} | {pct(x['median_generation_ratio'])} |")
    lines += ['', '## 含共享准备与加载（准备为既有共享成本，单列）', '',
              '| 划分 | 比较 | 中位省时 | 中位省秒 |', '|---|---|---:|---:|']
    for x in summary:
        lines.append(f"| {x['partition']} | {x['comparison']} | {pct(x['median_with_preparation_ratio'])} | {x['median_with_preparation_saved_seconds']:.3f} |")
    lines += ['', '## 退化护栏（B 轨迹；E/D 与之逐点相同）', '',
              '| 划分 | seed | 最终ACC | 最终NMI | 单簇客户端 | 最大簇均值 | 单客户端最大簇 | 教师边比例 | S1 | S2(20轮网格) | Q1 | Q2 | 通过 |',
              '|---|---:|---:|---:|---:|---:|---:|---:|:--:|:--:|:--:|:--:|:--:|']
    for g in guards:
        mark = lambda ok: '✓' if ok else '✗'  # noqa: E731
        lines.append(f"| {g['partition']} | {g['seed']} | {g['final_acc']:.4f} | {g['final_nmi']:.4f} | {g['final_single_clients']} "
                     f"| {g['final_mean_largest']:.4f} | {g['final_max_client_largest']:.4f} | {g['final_edge_fraction']:.4f} "
                     f"| {mark(g['S1'])} | {mark(g['S2'])} | {mark(g['Q1'])} | {mark(g['Q2'])} | {mark(g['passed'])} |")
    lines += ['', '代价明细（持久数组、进程峰值、前向端点、通信）见 runs.csv 与各运行 JSON。'
                  '公共预算从 8 步降至 2 步的成本减少不计作认证收益；串行总耗时不是并行轮时延。', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    return summary
