"""Summarize matched blocks and held-out seed results."""

from collections import defaultdict
from itertools import combinations
from statistics import mean

from experiments.snapshot_graph_scaling.design import cell_id
from ..confirmation.run import PARTITIONS, config
from ..on_demand.report import metrics
from ..report import eligible, write_csv
from .design import METHODS

CONTRASTS = tuple(combinations(METHODS[::-1], 2))


def summarize(groups, left, right, field):
    if not groups:
        return None, None, 0
    a, b = zip(*[(g[left][field], g[right][field]) for g in groups], strict=True)
    saved = mean(b)-mean(a)
    return saved, 100*saved/mean(b) if mean(b) else None, sum(x < y for x, y in zip(a, b, strict=True))


def report(out, manifest, groups, audits, blocked):
    full = manifest['preset'] == 'full'
    required = 4 if full else 1
    accepted, used = defaultdict(list), set()
    runs, pairs, cells, comparisons, widths, scope = [], [], [], [], [], []
    fields = ('head_seconds', 'generation_seconds', 'teacher_path_seconds', 'total_bytes')
    threshold, min_wins = manifest['threshold_pct'], manifest['minimum_wins']
    for block, attempt, group in groups:
        cell, repeat = cell_id(block['case']), block['repeat']
        clean = eligible(group, 'full' if full else 'smoke')
        take = clean and (cell, repeat) not in used
        base = dict(cell=cell, repeat=repeat, attempt=attempt, order='/'.join(block['order']), eligible=clean, primary=take)
        values = {m: metrics(group[m]) for m in METHODS}
        runs.extend(dict(**base, method=m, **values[m]) for m in METHODS)
        for left, right in CONTRASTS:
            row = dict(**base, method=left, reference=right)
            for field in fields:
                saved, pct, _ = summarize([values], left, right, field)
                row.update({f'{field}_saved': saved, f'{field}_saved_pct': pct})
            pairs.append(row)
        if take:
            used.add((cell, repeat))
            accepted[cell].append(values)
    decisions = {}
    for case in manifest['cases']:
        cell = cell_id(case)
        cohort = 'fresh' if case in manifest['fresh'] else 'historical'
        base = dict(cell=cell, **case, cohort=cohort)
        choices = accepted[cell]
        status = 'initialization_blocked' if cell in blocked else 'timing_incomplete' if len(choices) != required else 'complete'
        fastest = min(METHODS, key=lambda m: mean(g[m]['head_seconds'] for g in choices)) if status == 'complete' else ''
        fastest_time = mean(g[fastest]['head_seconds'] for g in choices) if fastest else None
        for method in METHODS:
            costs = {field: mean(g[method][field] for g in choices) if choices else None for field in
                     (*fields, 'cache_bytes', 'protocol_bytes', 'up_bytes', 'down_bytes', 'endpoints')}
            cells.append(dict(**base, method=method, blocks=len(choices), status=status, fastest=fastest,
                              head_seconds_above_fastest=None if fastest_time is None else costs['head_seconds']-fastest_time,
                              blocked_clients=blocked.get(cell, ''), **costs))
            if cell not in blocked:
                cfg = config(manifest['protocol'], case['seed'])
                for client, (width, count) in enumerate(zip(cfg['widths'], audits[cell, method]['client_endpoints'], strict=True)):
                    widths.append(dict(**base, method=method, client=client, width=width, endpoints=count,
                                       scoring_macs=count*width*cfg['classes']))
        if cell not in blocked:
            scope.extend(dict(**base, **row, edge_fraction=row['edges'] / (case['public_size']//2))
                         for row in audits[cell, 'Demand']['scope'])
        for left, right in CONTRASTS:
            row = dict(**base, method=left, reference=right, blocks=len(choices), status=status)
            for field in fields:
                saved, pct, wins = summarize(choices, left, right, field)
                row.update({f'{field}_saved': saved, f'{field}_saved_pct': pct, f'{field}_wins': wins})
            row['passes'] = (row['head_seconds_saved_pct'] >= threshold and row['head_seconds_wins'] >= min_wins
                             if full and status == 'complete' else None)
            comparisons.append(row)
            decisions[cell, left, right] = row
    for name, rows in [('runs', runs), ('paired_blocks', pairs), ('cells', cells), ('comparisons', comparisons),
                       ('client_widths', widths), ('demand_scope', scope)]:
        if rows:
            write_csv(out/f'{name}.csv', rows)
    audits_full = sum(r['comparisons'] for (_, m), r in audits.items() if m != 'Demand')
    audits_demand = sum(r['comparisons'] for (_, m), r in audits.items() if m == 'Demand')
    lines = ['# STL-10 同场景配对与规模边界', '',
             f'全图边核对 {audits_full:,} 次，Demand 请求边核对 {audits_demand:,} 次。'
             f'通过核对的计时进程 {len(runs)} 次，含补测。', '',
             '| 配置 | 种子组 | 有效块 | 完整头部均值最低 | D 对 B 省时 | D 对 E 省时 | Demand 对 D 省时 |',
             '|---|---|---:|---|---:|---:|---:|']

    def seconds_pct(row):
        x = row['head_seconds_saved_pct']
        return f'{x:+.2f}%' if x is not None else '—'

    for row in cells[::len(METHODS)]:
        cell = row['cell']
        contrasts = [seconds_pct(decisions[cell, m, b]) for m, b in [('D','B'), ('D','E'), ('Demand','D')]]
        lines.append(f"| {cell} | {row['cohort']} | {row['blocks']}/{required} | "
                     f"{row['fastest'] or row['status']} | {' | '.join(contrasts)} |")
    if full:
        lines.extend(['', '## M4096 新种子确认', ''])
        for part in PARTITIONS:
            ids = [cell_id(c) for c in manifest['fresh'] if c['partition'] == part]
            for left, right in [('D', 'B'), ('D', 'E')]:
                rows = [decisions[cell, left, right] for cell in ids]
                passed = sum(r['passes'] is True for r in rows)
                ready = all(r['status'] == 'complete' for r in rows)
                verdict = '证据不足' if not ready else '达标' if passed >= 2 else '未达标'
                lines.append(f'- {part}，{left}/{right} 达标种子 {passed}/{len(rows)}，划分判定{verdict}。')
    else:
        lines.extend(['', '合成短测用于核对程序与报表。'])
    if blocked:
        lines.extend(['', '## 初始化阻断', ''])
        lines.extend(f'- {cell}，未找到支持全部伪簇的客户端编号 {clients}。' for cell, clients in blocked.items())
    lines.extend(['', '完整头部包含初始化和全部训练轮。省时为右侧方法耗时减左侧方法耗时。'
                  '完整头部是整个配置的耗时。client_widths.csv 报告逐客户端教师端点及对应打分 MACs。'
                  '出于可重复性，进程峰值和计时筛选记录保留在 runs.csv。'])
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
