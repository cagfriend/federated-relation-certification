"""Report seed-level full-head savings and paired phase breakdowns."""

from collections import defaultdict
from math import isfinite
from statistics import mean, median

from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_graph_scaling.design import cell_id

from ..report import write_csv
from ..timing_diagnosis.probe import CLOCKS, PHASES

STAGES = ('head', 'setup', *PHASES, 'other')
FOCUS = '2023_dirichlet_0.1_m4096'


def totals(run, clock):
    rows = [row[clock] for row in run['rounds']]
    setup = run['setup'][clock]
    require(all(isfinite(value) and value >= 0 for row in rows for value in row.values()) and
            isfinite(setup) and setup >= 0, 'Invalid stage time')
    phases = {phase: sum(row[phase] for row in rows) for phase in PHASES}
    training = sum(row['total'] for row in rows)
    other = training - sum(phases.values())
    require(other >= -1e-8 and (clock != 'wall' or setup + training > 0), 'Invalid full-head total')
    return dict(head=setup + training, setup=setup, **phases, other=other)


def summarize(rows, stage):
    if not rows:
        return None, None, 0
    b = mean(row[f'b_wall_{stage}_s'] for row in rows)
    d = mean(row[f'd_wall_{stage}_s'] for row in rows)
    return b-d, 100*(b-d)/b if b else None, sum(row[f'wall_{stage}_saved_s'] > 0 for row in rows)


def report(out, manifest, pairs, audits):
    first, accepted = defaultdict(list), defaultdict(list)
    raw, paired, cells, quality = [], [], [], []
    for pair, group, clean in pairs:
        cell, repeat, attempt, order = (pair[key] for key in ('cell', 'repeat', 'attempt', 'order'))
        key = dict(cell=cell, repeat=repeat, attempt=attempt, order=order, eligible=clean)
        measured = {method: {clock: totals(run, clock) for clock in CLOCKS} for method, run in group.items()}
        for method, run in group.items():
            times = {f'{clock}_{stage}_s': seconds for clock, stages in measured[method].items()
                     for stage, seconds in stages.items()}
            raw.append(dict(**key, method=method, position=run['position'], **times,
                            endpoints=sum(row['endpoints'] for row in run['timing']),
                            up_bytes=run['traffic']['up_bytes'], down_bytes=run['traffic']['down_bytes'],
                            cache_bytes=run['cache_bytes'], protocol_bytes=run['protocol_bytes'],
                            input_peak_bytes=run['input_peak_bytes'], process_peak_bytes=run['process_peak_bytes'],
                            suspend_seconds=run['suspend_seconds'],
                            **{p: run['power'].get(p, 0) for p in ('ac', 'battery', 'unknown')}))
        row = dict(**key)
        for clock in CLOCKS:
            for stage in STAGES:
                b = measured['B'][clock][stage]
                d = measured['D'][clock][stage]
                row.update({f'b_{clock}_{stage}_s': b, f'd_{clock}_{stage}_s': d,
                            f'{clock}_{stage}_saved_s': b-d,
                            f'{clock}_{stage}_saved_pct': 100*(b-d)/b if b else None})
        paired.append(row)
        if attempt == 0:
            first[cell].append(row)
        if clean:
            accepted[cell].append(row)
    full = manifest['preset'] == 'full'
    planned = defaultdict(int)
    for block in manifest['schedule']:
        planned[block['cell']] += 1
    for case in manifest['cases']:
        cell = cell_id(case)
        originals, valid = first[cell], accepted[cell]
        require(len(originals) == planned[cell] and len(valid) == len({row['repeat'] for row in valid}),
                f'Incomplete or duplicate pairs for {cell}')
        for scope, rows in (('original', originals), ('eligible', valid)):
            status = '短测' if not full else '配对不足' if len(rows) != planned[cell] else '未达标'
            summary = dict(cell=cell, **case, scope=scope, pairs=len(rows))
            for stage in STAGES:
                seconds, percent, wins = summarize(rows, stage)
                summary.update({f'{stage}_saved_s': seconds, f'{stage}_saved_pct': percent, f'{stage}_wins': wins})
            if (status == '未达标' and summary['head_saved_pct'] >= manifest['head_threshold_pct'] and
                    summary['head_wins'] >= manifest['min_wins']):
                status = '达标'
            summary['b_generation_share_pct'] = (
                100*mean(row['b_wall_generation_s'] for row in rows)/mean(row['b_wall_head_s'] for row in rows)
                if rows else None)
            cells.append(dict(**summary, status=status))
    for audit in audits:
        for tick in audit['evaluations']:
            quality.extend(dict(cell=audit['cell'], round=tick['round'], **client) for client in tick['clients'])
    for name, rows in (('runs', raw), ('paired_blocks', paired), ('comparisons', cells), ('quality', quality)):
        write_csv(out / f'{name}.csv', rows)

    def fmt(value, digits=2):
        return '—' if value is None else f'{value:+.{digits}f}'

    eligible = [row for row in cells if row['scope'] == 'eligible']
    lines = ['# 偏置净变化 D 对 B 的完整头部计时', '',
             f'逐边审计 {sum(audit["comparisons"] for audit in audits):,} 次，零差异。'
             f'训练轨迹与应用层字节逐轮一致。独立计时进程 {len(raw)} 个，含补测。', '',
             '| 配置 | 合格配对 | 完整头部省秒 | 完整头部省时 % | D 更快 | 生成省时 % | 判定 |',
             '|---|---:|---:|---:|---:|---:|---|']
    for row in eligible:
        lines.append(f"| {row['cell']} | {row['pairs']}/{planned[row['cell']]} | {fmt(row['head_saved_s'], 4)} | "
                     f"{fmt(row['head_saved_pct'])} | {row['head_wins']}/{row['pairs']} | "
                     f"{fmt(row['generation_saved_pct'])} | {row['status']} |")
    if full:
        lines.extend(['', '## 按划分判定', ''])
        for partition in ('iid', 'dirichlet_0.1'):
            subset = [r for r in eligible if r['partition'] == partition]
            passed = sum(r['status'] == '达标' for r in subset)
            verdict = '配对不足' if any(r['status'] == '配对不足' for r in subset) else (
                '达标' if passed == len(subset) else '未达标')
            lines.append(f'- {partition}，{passed}/{len(subset)} 个种子达标，划分判定{verdict}。')
    else:
        lines.extend(['', '短测结果用于核对训练与报表流程。'])
    if FOCUS in planned:
        lines.extend(['', '## 强非 IID，seed 2023', '',
                      '| 重复 | 顺序 | 完整头部省秒 | 生成省秒 | 其余阶段合计省秒 |',
                      '|---:|---|---:|---:|---:|'])
        rows = accepted[FOCUS]
        for row in rows:
            total, generation = row['wall_head_saved_s'], row['wall_generation_saved_s']
            lines.append(f"| {row['repeat']} | {row['order']} | {fmt(total, 4)} | {fmt(generation, 4)} | "
                         f"{fmt(total-generation, 4)} |")
        if rows:
            median_generation = median(row['wall_generation_saved_s'] for row in rows)
            wins = sum(row['wall_generation_saved_s'] > 0 for row in rows)
            lines.extend(['', f'生成阶段配对省秒中位数 {fmt(median_generation, 4)}，D 更快 {wins}/{len(rows)} 对。'])
        lines.extend(['', 'E49 的异常来自新版 D 对旧版 D 的回放。本表比较新版 D 对全量 B 的实时训练。'])
    lines.extend(['', '完整头部计入初始化和所有训练轮。正值表示 D 省时。'
                  '共同准备、外部审计及评估在计时区间外。'
                  '原始及合格配对、逐阶段墙钟和进程 CPU 时间均保存在 CSV。'
                  '逐客户端 ACC、NMI、ARI 和簇占用见 quality.csv。'])
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
