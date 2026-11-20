"""Fit on whole training seeds and report matched, measured net costs."""

from collections import defaultdict
import csv
from statistics import mean, median

from .replay import METHODS, POLICY

FIXED = METHODS[:3]


def repeats(preset):
    return 3 if preset == 'full' else 1


def blocks(runs):
    result = defaultdict(dict)
    for run in runs:
        result[run['cell'], run['repeat']][run['method']] = run
    return result


def eligible(group, preset):
    return preset == 'smoke' or all(r['power'].get('ac', 0) and not r['power'].get('battery', 0)
                                    and not r['power'].get('unknown', 0)
                                    and r['suspend_seconds'] is not None and r['suspend_seconds'] < 1.
                                    for r in group.values())


def client_seconds(run):
    share = run['setup_seconds']/len(run['selections'])
    return [sum(times)+share for times in zip(*(row['clients'] for row in run['rows']))]


def seconds(run):
    return run['setup_seconds'] + sum(row['seconds'] for row in run['rows'])


def fit(cases, configs, runs, preset):
    from experiments.snapshot_graph_scaling.design import cell_id

    observations = defaultdict(lambda: defaultdict(list))
    for (cell, _), group in blocks(runs).items():
        if not eligible(group, preset):
            continue
        cfg = configs[cell]
        costs = {m: client_seconds(group[m]) for m in FIXED}
        for i, width in enumerate(cfg['widths']):
            observations[cfg['public_size'], width][cfg['seed']].append({
                m: costs[m][i] / costs['B'][i] for m in FIXED})
    tables = {}
    for case in cases:
        cell = cell_id(case)
        cfg = configs[cell]
        table = {}
        for width in set(cfg['widths']):
            train = {seed: {m: median(row[m] for row in rows) for m in FIXED}
                     for seed, rows in observations[cfg['public_size'], width].items() if seed != cfg['seed']}
            if not train:
                # Smoke deliberately exercises dual-cache execution with no timing-based fit.
                table[str(width)] = dict(first='B', second='D' if preset == 'smoke' else None,
                                         trial_cost=0., possible_gain=0., training_seeds=[])
                continue
            ratios = {m: median(row[m] for row in train.values()) for m in FIXED}
            # Use B as the tie preference, then E. Consider only one challenger.
            first, second, _ = sorted(FIXED, key=lambda m: (ratios[m], FIXED.index(m)))
            possible = max(max(0., row[first]-row[second]) for row in train.values())
            uncertain = (ratios[second] <= ratios[first]*POLICY['close_ratio'] or possible > 0)
            table[str(width)] = dict(first=first, second=second if uncertain else None, ratios=ratios,
                                     trial_cost=max(row[second] for row in train.values()), possible_gain=possible,
                                     training_seeds=sorted(train))
        tables[cell] = table
    return tables


def write_csv(path, records):
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def build(out, cases, configs, runs, preset):
    from experiments.snapshot_graph_scaling.design import cell_id

    grouped = blocks(runs)
    raw, cells = [], []
    for (cell, rep), group in sorted(grouped.items()):
        clean = eligible(group, preset)
        for method, r in group.items():
            raw.append(dict(cell=cell, repeat=rep, method=method, matched_power_and_suspend_ok=clean,
                            net_seconds=seconds(r), setup_seconds=r['setup_seconds'],
                            first_round_seconds=r['rows'][0]['seconds'],
                            trial_seconds=sum(s['trial_seconds'] for s in r['selections']),
                            initial_routes=' '.join(s['initial'] for s in r['selections']),
                            final_routes=' '.join(s['final'] for s in r['selections']),
                            decisions=' '.join(s['reason'] for s in r['selections']),
                            peak_cache_bytes=r['peak_cache_bytes'], final_cache_bytes=r['final_cache_bytes'],
                            process_peak_bytes=r['process_peak_bytes'],
                            input_peak_bytes=r['input_peak_bytes'], ac=r['power'].get('ac', 0),
                            battery=r['power'].get('battery', 0), unknown=r['power'].get('unknown', 0),
                            suspend_seconds=r['suspend_seconds'], exact_edges=r['comparisons'],
                            exact_trial_edges=r['probe_comparisons']))
    for c in cases:
        cell = cell_id(c)
        for scope in ('all', 'power_checked'):
            subset = [g for (k, _), g in grouped.items()
                      if k == cell and (scope == 'all' or eligible(g, preset))]
            if not subset:
                continue
            totals = {m: mean(seconds(g[m]) for g in subset) for m in METHODS}
            # A client's offline reference picks once using the full sequence averaged across repeats.
            per_client = list(zip(*(list(map(mean, zip(*(client_seconds(g[m]) for g in subset))))
                                    for m in FIXED)))
            oracle = sum(map(min, per_client))
            for method in METHODS:
                client_total = mean(sum(client_seconds(g[method])) for g in subset)
                cells.append(dict(cell=cell, seed=c['seed'], partition=c['partition'], public_size=c['public_size'],
                                  scope=scope, paired_blocks=len(subset), method=method,
                                  net_seconds=totals[method], vs_B_pct=(1-totals[method]/totals['B'])*100,
                                  vs_S_pct=(1-totals[method]/totals['S'])*100,
                                  wins_vs_B=sum(seconds(g[method]) < seconds(g['B']) for g in subset),
                                  wins_vs_E=sum(seconds(g[method]) < seconds(g['E']) for g in subset),
                                  wins_vs_S=sum(seconds(g[method]) < seconds(g['S']) for g in subset),
                                  vs_E_pct=(1-totals[method]/totals['E'])*100,
                                  offline_client_oracle_seconds=oracle,
                                  extra_client_seconds=client_total-oracle,
                                  extra_client_pct=(client_total/oracle-1)*100))
    write_csv(out/'runs.csv', raw)
    write_csv(out/'boundaries.csv', cells)
    formal = [r for r in cells if r['scope'] == 'power_checked' and r['paired_blocks'] >= 2]
    lines = ['# 精确关系选路的成本边界', '',
             '完整 E40 教师轨迹固定。耗时包含本地路径决策、缓存初始化、稳态生成和实际试跑。',
             '报告口径为教师关系生成重放。完整头部训练与底层通信的实测属于后续阶段。', '',
             f'主要输出关系逐边检查 {sum(r["exact_edges"] for r in raw):,} 次，'
             f'试跑路径额外检查 {sum(r["exact_trial_edges"] for r in raw):,} 次，全部一致。', '',
             '`boundaries.csv` 同时列出全部块和通过电源与休眠检查的配对块。',
             '每客户端的事后参照在整条轨迹内固定一种路径。负的额外秒数可能来自计时波动或一次切换。',
             '低于两块的格子保留描述性结果。', '']
    if preset == 'smoke':
        lines.append('此为合成 smoke，验证数据流、缓存与精确性。')
    else:
        lines += ['| 配置 | 配对块 | D 对 B 省时 | D 对 E 省时 | S 对 B 省时 | C 对 B 省时 | C 对 S 省时 |',
                  '|---|---:|---:|---:|---:|---:|---:|']
        for cell in dict.fromkeys(r['cell'] for r in formal):
            view = {r['method']: r for r in formal if r['cell'] == cell}
            d, s, c = (view[m] for m in ('D', 'S', 'C'))
            values = (d['vs_B_pct'], d['vs_E_pct'], s['vs_B_pct'], c['vs_B_pct'], c['vs_S_pct'])
            lines.append(f"| {cell} | {d['paired_blocks']} | " + ' | '.join(f'{x:+.2f}%' for x in values) + ' |')
        if not formal:
            lines += ['', '没有配置达到最少两组电源与休眠检查完整的配对块。']
        lines += ['', '| M | 可判定格 | D 同时快于 B/E | S 快于 B | C 快于 B | C 快于 S |',
                  '|---:|---:|---:|---:|---:|---:|']
        for size in sorted({cfg['public_size'] for cfg in configs.values()}):
            d, s, c = ([r for r in formal if r['public_size'] == size and r['method'] == m]
                       for m in ('D', 'S', 'C'))
            def passes(row, baseline):
                return row[f'vs_{baseline}_pct'] >= 3 and row[f'wins_vs_{baseline}'] >= 2
            counts = (sum(passes(r, 'B') and passes(r, 'E') for r in d),
                      sum(passes(r, 'B') for r in s),
                      sum(passes(r, 'B') for r in c),
                      sum(passes(r, 'S') for r in c))
            lines.append(f'| {size} | {len(d)} | ' + ' | '.join(map(str, counts)) + ' |')
        lines += ['', '表中快于指配对均值至少省 3%，且至少赢两块。',
                  '当前结果是按整 seed 留出的开发筛查。独立种子的确认与完整训练计时另行评估。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
