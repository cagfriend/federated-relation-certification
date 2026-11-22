"""Combine balanced replay timings and phase profiles without mixing their clocks."""

from collections import defaultdict
from statistics import mean, median

from ..report import write_csv
from .worker import METHODS

LABELS = {'D': '当前 D', 'W': '仅权重区间', 'S': '仅相消防护', 'C': '合并版'}
PHASES = ('initialization', 'advance', 'candidate', 'scale', 'refresh', 'dense', 'other')


def report(out, manifest, blocks):
    timing, profiles, raw, groups, cells = [], [], [], [], []
    selected = defaultdict(list)
    for slot, methods in blocks:
        key = {k: slot[k] for k in ('cell', 'repeat', 'order', 'attempt', 'eligible')}
        times = {}
        for method in METHODS:
            run = methods[method]
            rows = run['rows']
            seconds = sum(row['seconds'] for row in rows)
            times[method] = seconds
            common = dict(**key, method=method, seconds=seconds, initialization_seconds=rows[0]['seconds'],
                          mismatches=sum(sum(row['mismatches']) for row in rows),
                          edges_checked=run['edge_comparisons'],
                          endpoints=sum(sum(row['endpoints']) for row in rows),
                          scoring_macs=sum(row['scoring_macs'] for row in rows), cache_bytes=run['cache_bytes'],
                          scale_fallbacks=run['scale_fallbacks'], rebuilds=run['rebuilds'],
                          power_start=run['power'][0], power_end=run['power'][1], suspend_seconds=run['suspend_seconds'])
            raw.append(common)
            if 'phases' in run:
                profiles.append(dict(**common, **{f'{name}_seconds': run['phases'][name]
                                                  for name in PHASES if name != 'initialization'}))
            else:
                timing.append(common)
        if slot['repeat']:
            group = dict(**key, **{f'{m}_seconds': times[m] for m in METHODS},
                         **{f'{m}_delta_s': times[m]-times['D'] for m in METHODS[1:]},
                         **{f'{m}_delta_pct': 100*(times[m]/times['D']-1) for m in METHODS[1:]},
                         interaction_s=times['C']-times['W']-times['S']+times['D'])
            groups.append(group)
            if slot['eligible']:
                selected[slot['cell']].append(group)
    phase_delta = []
    for cell, trace in manifest['traces'].items():
        valid = selected[cell]
        planned = sum(b['cell'] == cell and b['repeat'] > 0 for b in manifest['schedule'])
        for method in METHODS[1:]:
            pairs = [(group[f'{method}_seconds'], group['D_seconds']) for group in valid]
            measurements = [row for row in timing if row['cell'] == cell and row['method'] == method]
            cells.append(dict(cell=cell, **trace['case'], rounds=trace['rounds'], method=method,
                              eligible_blocks=len(valid), planned_blocks=planned,
                              delta_s=mean(a-b for a,b in pairs) if pairs else None,
                              delta_pct=100*(sum(a for a,b in pairs)/sum(b for a,b in pairs)-1) if pairs else None,
                              median_delta_s=median(a-b for a,b in pairs) if pairs else None,
                              slower_blocks=sum(a>b for a,b in pairs),
                              interaction_s=mean(row['interaction_s'] for row in valid) if valid else None,
                              mismatches=measurements[0]['mismatches'], endpoints=measurements[0]['endpoints'],
                              cache_bytes=measurements[0]['cache_bytes'],
                              scale_fallbacks=measurements[0]['scale_fallbacks'], rebuilds=measurements[0]['rebuilds']))
        available = {r['method']: r for r in profiles if r['cell'] == cell and r['eligible']}
        for method in METHODS[1:]:
            if method not in available or 'D' not in available:
                continue
            for phase in PHASES:
                base = available['D'][f'{phase}_seconds']
                other = available[method][f'{phase}_seconds']
                phase_delta.append(dict(cell=cell, method=method, phase=phase, D_seconds=base, method_seconds=other,
                                        delta_seconds=other-base))

    def fmt(value, spec):
        return '—' if value is None else format(value, spec)

    lines = ['# 权重区间与相消防护的开销消融', '',
             '| 配置 | 防护 | 合格块 | 较 D 增加毫秒 | 相对 D 增加 % | 更慢的块 | 对 B 错边 | 全批回退 | 重建 |',
             '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for row in cells:
        millis = None if row['delta_s'] is None else row['delta_s']*1e3
        lines.append(f"| {row['cell']} | {LABELS[row['method']]} | {row['eligible_blocks']}/{row['planned_blocks']} | "
                     f"{fmt(millis, '+.2f')} | {fmt(row['delta_pct'], '+.2f')} | {row['slower_blocks']} | "
                     f"{row['mismatches']} | {row['scale_fallbacks']} | {row['rebuilds']} |")
    lines.extend(['', '## 独立阶段计时', '',
                  '| 配置 | 防护 | 初始化 Δms | 累计 Δms | 候选 Δms | 尺度检测 Δms | 局部重打分 Δms | 全批回退 Δms | 其他 Δms |',
                  '|---|---|---:|---:|---:|---:|---:|---:|---:|'])
    deltas = defaultdict(dict)
    for row in phase_delta:
        deltas[row['cell'], row['method']][row['phase']] = row['delta_seconds']
    for (cell, method), values in deltas.items():
        phase_text = ' | '.join(f'{values[phase]*1e3:+.2f}' for phase in PHASES)
        lines.append(f"| {cell} | {LABELS[method]} | {phase_text} |")
    if not deltas:
        lines.append('| — | 无合格阶段计时 | — | — | — | — | — | — | — |')
    lines.extend(['', '总耗时来自未插桩的独立重放。阶段耗时来自另一次插桩重放，'
                  '覆盖第 1 轮初始化及后续生成。全批回退阶段包含覆盖全批的打分和缓存重建。'
                  '尺度检测的首次调用计入初始化。各方法的前向端点、MACs、缓存及与 B 的逐边核对见 runs.csv。'
                  '交互项 C−W−S+D 见 blocks.csv。'])
    if manifest['preset'] == 'smoke':
        lines.extend(['', '本次为 10 轮短测。'])
    if any(r['mismatches'] for r in raw):
        lines.extend(['', '有方法在当前存档轨迹上出现对 B 的硬关系差异。对应原始 JSON 保存首次差异轮次、客户端与边编号。'])
    paths = []
    for name, rows in (('cells', cells), ('blocks', groups), ('runs', raw), ('phases', profiles),
                       ('phase_deltas', phase_delta)):
        if rows:
            path = out/f'{name}.csv'
            write_csv(path, rows)
            paths.append(path)
    path = out/'report.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return [*paths, path]
