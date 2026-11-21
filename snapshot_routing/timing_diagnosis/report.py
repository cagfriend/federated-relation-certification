"""Pair the four-run blocks and quantify the observed same-method variation."""

from collections import defaultdict
from statistics import mean, median, quantiles

from ..report import eligible, write_csv
from .probe import CLOCKS, PHASES

TIME_FIELDS = ('head', 'non_generation', 'setup', *PHASES, 'remainder')


def totals(run, clock):
    rows = [row[clock] for row in run['rounds']]
    head = run['setup'][clock] + sum(r['total'] for r in rows)
    phases = {k: sum(r[k] for r in rows) for k in PHASES}
    return dict(head=head, non_generation=head-phases['generation'], setup=run['setup'][clock], **phases,
                remainder=head-run['setup'][clock]-sum(phases.values()))


def paired_metrics(runs, clock):
    values = [totals(r, clock) for r in runs]
    order = ''.join(r['method'] for r in runs)
    by_method = {m: [a for a, k in zip(values, order, strict=True) if k == m] for m in 'BD'}
    block = {f'{name}_delta_seconds': mean(v[name] for v in by_method['D'])
             - mean(v[name] for v in by_method['B']) for name in TIME_FIELDS}
    block['b_head_seconds'] = mean(v['head'] for v in by_method['B'])
    noise = []
    for index, (a, b) in enumerate(zip(order, order[1:])):
        if a == b:
            noise.append(dict(method=a, left_position=index+1, right_position=index+2,
                              **{f'{name}_abs_seconds': abs(values[index][name]-values[index+1][name])
                                 for name in TIME_FIELDS}))
    return block, noise


def diagnostic(predictions, controls, field, manifest):
    name = field+'_delta_seconds'
    effects = [row[name] for row in predictions]
    variability = [row[field+'_abs_seconds'] for row in controls]
    q90 = (quantiles(variability, n=10, method='inclusive')[8] if len(variability) > 1
           else variability[0] if variability else None)
    center = median(effects) if effects else None
    directions = {m: sum(row['first'] == m and row[name] > 0. for row in predictions) for m in 'BD'}
    sufficient = len(predictions) == manifest['blocks_per_cell']
    signal = (sufficient and q90 is not None and center > q90 and
              min(directions.values()) >= manifest['same_direction_per_order'])
    status = ('smoke' if manifest['preset'] == 'smoke' else 'incomplete' if not sufficient
              else 'extra_time_detected' if signal else 'threshold_not_met')
    return dict(median_extra_seconds=center, q90_same_method_seconds=q90, blocks=len(predictions),
                controls_b=sum(c['method'] == 'B' for c in controls),
                controls_d=sum(c['method'] == 'D' for c in controls),
                d_slower_b_first=directions['B'], d_slower_d_first=directions['D'], status=status)


def report(out, runs, manifest):
    groups = defaultdict(list)
    for run in runs:
        groups[run['cell'], run['block'], run['attempt']].append(run)
    raw, blocks, controls, stages = [], [], [], []
    chosen = set()
    for (cell, block, attempt), group in sorted(groups.items()):
        group.sort(key=lambda r: r['position'])
        clean = eligible(dict(enumerate(group)), manifest['preset'])
        selected = clean and (cell, block) not in chosen
        if selected:
            chosen.add((cell, block))
        order = ''.join(r['method'] for r in group)
        base = dict(cell=cell, block=block, attempt=attempt, order=order, first=order[0],
                    clean=clean, selected=selected)
        for clock in CLOCKS:
            values, noise = paired_metrics(group, clock)
            blocks.append(dict(base, clock=clock, **values))
            controls.extend(dict(base, clock=clock, **record) for record in noise)
            for r in group:
                raw.append(dict(base, clock=clock, method=r['method'], position=r['position'],
                                **totals(r, clock), peak_bytes=r['process_peak_bytes'],
                                cache_bytes=r['cache_bytes'], ac=r['power'].get('ac', 0),
                                battery=r['power'].get('battery', 0), unknown=r['power'].get('unknown', 0),
                                suspend_seconds=r['suspend_seconds']))
    header = ['# 完整头部训练计时归因', '',
              f'完成 {len(runs)} 次独立进程计时，包括补测。',
              '每块用两个 D 的平均耗时减去两个 B 的平均耗时。表中差值为正表示 D 多用时。',
              '其他阶段指完整头部耗时减去关系生成耗时。', '',
              '| 配置 | 计时 | 有效块 | 生成省秒中位数 | 其他阶段多用秒中位数 | 同法差 Q90 | 完整头部净省秒中位数 | 诊断 |',
              '|---|---|---:|---:|---:|---:|---:|---|']
    for cell in manifest['cells']:
        for clock in CLOCKS:
            pred = [b for b in blocks if b['cell'] == cell and b['clock'] == clock and b['selected']]
            ctl = [b for b in controls if b['cell'] == cell and b['clock'] == clock and b['selected']]
            for field in TIME_FIELDS:
                item = dict(cell=cell, clock=clock, phase=field, **diagnostic(pred, ctl, field, manifest))
                stages.append(item)
            item = diagnostic(pred, ctl, 'non_generation', manifest)
            gen = -median(b['generation_delta_seconds'] for b in pred) if pred else None
            head = -median(b['head_delta_seconds'] for b in pred) if pred else None
            fmt = lambda value: 'NA' if value is None else f'{value:+.4f}'
            header.append(f"| {cell} | {clock} | {len(pred)} | {fmt(gen)} | "
                          f"{fmt(item['median_extra_seconds'])} | {fmt(item['q90_same_method_seconds'])} | "
                          f"{fmt(head)} | {item['status']} |")
    header += ['', '## 完整头部墙钟的实用门槛', '',
               '| 配置 | 有效块 | 块均值省时 | D 胜出块 | 是否至少省 3% |',
               '|---|---:|---:|---:|---|']
    for cell in manifest['cells']:
        rows = [b for b in blocks if b['cell'] == cell and b['clock'] == 'wall' and b['selected']]
        pct = -100*mean(b['head_delta_seconds'] for b in rows)/mean(b['b_head_seconds'] for b in rows) if rows else None
        wins = sum(b['head_delta_seconds'] < 0. for b in rows)
        status = ('smoke' if manifest['preset'] == 'smoke' else '证据不足'
                  if len(rows) != manifest['blocks_per_cell'] else
                  '达到' if pct >= manifest['head_threshold_pct'] else '未达到')
        value = 'NA' if pct is None else f'{pct:+.2f}%'
        header.append(f'| {cell} | {len(rows)} | {value} | {wins} | {status} |')
    header += ['', '分阶段明细见 stage_diagnosis.csv。原始尝试、有效性和所用块见 block_metrics.csv。',
               'CPU 时钟的实际分辨率会影响短阶段，逐进程原始记录保留。']
    for name, rows in [('runs', raw), ('block_metrics', blocks), ('same_method', controls), ('stage_diagnosis', stages)]:
        write_csv(out/f'{name}.csv', rows)
    (out/'report.md').write_text('\n'.join(header)+'\n', encoding='utf-8')
