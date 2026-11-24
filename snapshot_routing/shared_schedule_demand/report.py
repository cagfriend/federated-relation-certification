"""Expose byte accounting and paired full-head/coordination timing separately."""

from collections import defaultdict
from statistics import mean

from experiments.snapshot_certification_timing.design import sha
from experiments.snapshot_graph_scaling.design import cell_id
from ..on_demand.report import compare, metrics
from ..report import write_csv
from .design import ORDERS
from .worker import EXPLICIT, SHARED, shared_accounting


def report(out, manifest, groups, audits, blocked):
    accepted = defaultdict(list)
    runs, pairs, cells, ledger, reconstruction = [], [], [], [], []
    contrasts = ((SHARED, EXPLICIT), (SHARED, 'D'), (EXPLICIT, 'D'))
    full = manifest['preset'] == 'full'
    repeats = len(ORDERS) if full else 1
    margin = manifest['head_margin_pct']
    wins_required = manifest['minimum_wins']

    for block, attempt, clean, group in groups:
        cell = cell_id(block['case'])
        base = dict(cell=cell, repeat=block['repeat'], attempt=attempt,
                    order='/'.join(block['order']), eligible=clean)
        values = {m: metrics(run) for m, run in group.items()}
        runs.extend(dict(**base, method=m, **value) for m, value in values.items())
        pairs.extend(dict(**base, method=a, reference=b, **compare([values], a, b)) for a, b in contrasts)
        if clean:
            accepted[cell].append(values)

    lines = ['# 共享日程 Demand 与全图、显式请求对照', '',
             '应用层总字节包含图注册和日程注册。完整头部计入初始化与训练各轮。'
             '表中正的省时表示共享日程版更快。', '',
             '| 配置 | 有效块 | 共享版相对显式版省字节 | 共享版相对 D 省字节 | '
             '共享版相对显式版头部省时 | 共享版相对 D 头部省时 | 协调阶段增时（秒） |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']

    def pct(value):
        return '—' if value is None else f'{value:+.2f}%'

    complete = not blocked
    for case in manifest['cases']:
        cell = cell_id(case)
        blocks = accepted[cell]
        ready = len(blocks) == repeats
        complete &= ready
        if cell in blocked:
            lines.append(f'| {cell} | 初始化受阻 | — | — | — | — | — |')
            continue
        shared, explicit, d = (audits[cell, method] for method in (SHARED, EXPLICIT, 'D'))
        byte_account = shared_accounting(explicit, shared)
        raw_bytes = {name: row['traffic']['total_bytes']
                     for name, row in [('shared', shared), ('explicit', explicit), ('d', d)]}
        byte_pct = {b: 100*(raw_bytes[b]-raw_bytes['shared'])/raw_bytes[b] for b in ('explicit', 'd')}
        ledger.append(dict(cell=cell, **{f'{name}_total_bytes': count for name, count in raw_bytes.items()},
                           shared_vs_explicit_byte_saved_pct=byte_pct['explicit'],
                           shared_vs_d_byte_saved_pct=byte_pct['d'], **byte_account))
        reconstruction.extend(dict(cell=cell, **r) for r in shared['schedule_diagnostics'])

        delta = {}
        for left, right in contrasts:
            result = compare(blocks, left, right)
            delta[left, right] = result['head_seconds_saved_pct']
            within_margin = sum(g[left]['head_seconds'] <= (1+margin/100)*g[right]['head_seconds'] for g in blocks)
            passes = None
            if ready and full and left == SHARED:
                if right == EXPLICIT:
                    passes = result['head_seconds_saved_pct'] >= -margin and within_margin >= wins_required
                if right == 'D':
                    passes = result['head_seconds_saved_pct'] >= margin and result['head_seconds_wins'] >= wins_required
            cells.append(dict(cell=cell, **case, method=left, reference=right, eligible_blocks=len(blocks),
                              within_head_margin=within_margin, head_criterion_passed=passes, **result))
        coordination = (mean(g[SHARED]['coordination_seconds']-g[EXPLICIT]['coordination_seconds'] for g in blocks)
                        if blocks else None)
        lines.append(f'| {cell} | {len(blocks)}/{repeats} | {pct(byte_pct["explicit"])} | {pct(byte_pct["d"])} | '
                     f'{pct(delta[SHARED, EXPLICIT])} | {pct(delta[SHARED, "D"])} | '
                     + ('—' if coordination is None else f'{coordination:+.4f}') + ' |')

    if full:
        lines.extend(['', '## 预设判据', ''])
        for part in ('iid', 'dirichlet_0.1'):
            for reference in (EXPLICIT, 'D'):
                subset = [r for r in cells if r['method'] == SHARED and r['reference'] == reference
                          and r['partition'] == part]
                expected = sum(c['partition'] == part for c in manifest['cases'])
                passed = sum(r['head_criterion_passed'] is True for r in subset)
                lines.append(f'- {part}，共享版对 {reference} 的完整头部判据通过 {passed}/{expected} 格。')
        lines.extend(['', '对显式版要求平均增时不超过 3%，且至少 4/6 个块的增时不超过 3%。'
                      '对 D 要求平均省时至少 3%，且至少赢 4/6 块。各划分单列。'])
    else:
        lines.extend(['', '合成短测用于检查消息、轨迹和计时流程。'])
    if blocked:
        lines.extend(['', f'初始化受阻的客户端记录保留在完成清单关联的 inputs.json，涉及 {len(blocked)} 格。'])
    lines.extend(['', '通信流水以 bytes.csv 为准，分别列出省下的请求和并集、注册成本及净节省。'
                  'reconstruction.csv 中的单端归因来自独立审计，正式完整头部计时使用无诊断插桩进程。'])

    files = {}
    for name, rows in [('runs.csv', runs), ('paired_blocks.csv', pairs), ('cells.csv', cells),
                       ('bytes.csv', ledger), ('reconstruction.csv', reconstruction)]:
        if rows:
            path = out/name
            write_csv(path, rows)
            files[name] = sha(path)
    path = out/'report.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return {**files, path.name: sha(path)}, complete
