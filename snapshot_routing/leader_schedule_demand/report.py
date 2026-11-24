"""Report paired head times and the exact request, union and registration ledger."""

from collections import defaultdict
from statistics import mean

from experiments.snapshot_certification_timing.design import sha
from experiments.snapshot_graph_scaling.design import cell_id
from ..on_demand.report import compare, metrics
from ..report import write_csv
from ..shared_schedule_demand.design import ORDERS
from .worker import EXPLICIT, LEADER, leader_accounting


def report(out, manifest, groups, audits):
    contrasts = ((LEADER, EXPLICIT), (LEADER, 'D'), (EXPLICIT, 'D'))
    full = manifest['preset'] == 'full'
    repeats = len(ORDERS) if full else 1
    margin = manifest['head_margin_pct']
    min_wins = manifest['minimum_wins']
    accepted = defaultdict(list)
    runs, pairs, cases, ledger, diagnostics = [], [], [], [], []
    for block, attempt, clean, data in groups:
        cell = cell_id(block['case'])
        base = dict(cell=cell, repeat=block['repeat'], attempt=attempt, eligible=clean,
                    order='/'.join(block['order']))
        values = {method: metrics(run) for method, run in data.items()}
        runs.extend(dict(**base, method=method, **value) for method, value in values.items())
        pairs.extend(dict(**base, method=a, reference=b, **compare([values], a, b)) for a, b in contrasts)
        if clean:
            accepted[cell].append(values)

    lines = ['# 仅聚合者重建请求的 Demand 对照', '',
             '正值表示仅聚合者重建版比对照更省。总字节含图注册和日程注册。', '',
             '| 配置 | 有效块 | 相对显式版省字节 | 相对 D 省字节 | 相对显式版头部省时 | '
             '相对 D 头部省时 | 协调阶段增时（秒） |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']

    def pct(value):
        return '—' if value is None else f'{value:+.2f}%'

    complete = True
    for case in manifest['cases']:
        cell = cell_id(case)
        blocks = accepted[cell]
        ready = len(blocks) == repeats
        complete &= ready
        leader, explicit, d = (audits[cell][method] for method in (LEADER, EXPLICIT, 'D'))
        totals = {label: row['traffic']['total_bytes']
                  for label, row in [('leader', leader), ('explicit', explicit), ('d', d)]}
        byte_pct = {label: 100*(totals[label]-totals['leader'])/totals[label] for label in ('explicit', 'd')}
        ledger.append(dict(cell=cell, **{f'{key}_total_bytes': val for key, val in totals.items()},
                           leader_vs_explicit_byte_saved_pct=byte_pct['explicit'],
                           leader_vs_d_byte_saved_pct=byte_pct['d'], **leader_accounting(explicit, leader)))
        diagnostics.extend(dict(cell=cell, **r) for r in leader['schedule_diagnostics'])
        deltas = {}
        for left, right in contrasts:
            comparison = compare(blocks, left, right)
            deltas[left, right] = comparison['head_seconds_saved_pct']
            count_in_margin = sum(g[left]['head_seconds'] <= g[right]['head_seconds']*(1+margin/100)
                                  for g in blocks)
            passes = None
            if ready and full and left == LEADER:
                if right == EXPLICIT:
                    passes = comparison['head_seconds_saved_pct'] >= -margin and count_in_margin >= min_wins
                else:
                    passes = (comparison['head_seconds_saved_pct'] >= margin
                              and comparison['head_seconds_wins'] >= min_wins)
            cases.append(dict(cell=cell, **case, method=left, reference=right, eligible_blocks=len(blocks),
                              within_head_margin=count_in_margin, head_criterion_passed=passes, **comparison))
        coordination = (mean(g[LEADER]['coordination_seconds']-g[EXPLICIT]['coordination_seconds'] for g in blocks)
                        if blocks else None)
        lines.append(f'| {cell} | {len(blocks)}/{repeats} | {pct(byte_pct["explicit"])} | {pct(byte_pct["d"])} | '
                     f'{pct(deltas[LEADER, EXPLICIT])} | {pct(deltas[LEADER, "D"])} | '
                     + ('—' if coordination is None else f'{coordination:+.4f}') + ' |')

    if full:
        lines.extend(['', '## 预设判据', ''])
        for part in ('iid', 'dirichlet_0.1'):
            for reference in (EXPLICIT, 'D'):
                subset = [r for r in cases if r['partition'] == part and r['method'] == LEADER
                          and r['reference'] == reference]
                lines.append(f'- {part}，相对 {reference} 的完整头部判据通过 '
                             f'{sum(r["head_criterion_passed"] is True for r in subset)}/{len(subset)} 格。')
        lines.extend(['', '显式版对照要求平均增时不超过 3%，且至少 4/6 块在此范围。'
                          '全图 D 对照要求平均省时至少 3% 且至少赢 4/6 块。'])
    else:
        lines.extend(['', '合成短测用于检查协议、轨迹和计时流程。'])
    lines.extend(['', '只有聚合者补算同伴请求。并集位图、投票、返回目标和逐轮回执沿用原协议。'
                      '重建时间的独立审计见 reconstruction.csv，无插桩配对见 paired_blocks.csv。'])

    files = {}
    for name, rows in [('bytes.csv', ledger), ('cells.csv', cases), ('runs.csv', runs),
                       ('paired_blocks.csv', pairs), ('reconstruction.csv', diagnostics)]:
        if rows:
            path = out/name
            write_csv(path, rows)
            files[name] = sha(path)
    path = out/'report.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return {**files, path.name: sha(path)}, complete
