"""Summarize timing blocks and quality without conditioning timing on accuracy."""

from statistics import mean

from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_graph_scaling.design import cell_id

from ..report import blocks, eligible, seconds, write_csv

METHODS = 'BED'


def compare(pairs, left, right, minimum, wins_needed):
    if not pairs:
        return dict(savings_pct=None, savings_seconds=None, paired_wins=0, passes=False)
    left_times = [seconds(g[left]) for g in pairs]
    right_times = [seconds(g[right]) for g in pairs]
    a, b = mean(left_times), mean(right_times)
    wins = sum(x < y for x, y in zip(left_times, right_times, strict=True))
    return dict(savings_pct=100*(1-a/b), savings_seconds=b-a, paired_wins=wins,
                passes=1-a/b >= minimum and wins >= wins_needed)


def report(out, cases, traces, runs, rule, manifest):
    preset = manifest['preset']
    minimum, wins_needed = manifest['relative_threshold'], manifest['min_wins']
    repeats = manifest['paired_repeats']
    grouped = blocks(runs)
    raw, comparisons, cells, quality_rows = [], [], [], []
    for (cell, repeat), group in sorted(grouped.items()):
        require(set(group) == set(METHODS), f'Unpaired timing block: {cell}/{repeat}')
        power_ok = eligible(group, preset)
        for method, r in group.items():
            raw.append(dict(cell=cell, repeat=repeat, method=method, eligible=power_ok, net_seconds=seconds(r),
                            setup_seconds=r['setup_seconds'], first_round_seconds=r['rows'][0]['seconds'],
                            peak_cache_bytes=r['peak_cache_bytes'], input_peak_bytes=r['input_peak_bytes'],
                            process_peak_bytes=r['process_peak_bytes'], suspend_seconds=r['suspend_seconds'],
                            ac=r['power'].get('ac', 0), battery=r['power'].get('battery', 0),
                            unknown=r['power'].get('unknown', 0), comparisons=r['comparisons'],
                            forward_endpoints=sum(sum(q['endpoints']) for q in r['rows'])))
    for case in cases:
        cell = cell_id(case)
        trace = traces[cell]
        chosen = rule[case['public_size']]
        row = dict(cell=cell, **case, rule_path=chosen, blocked_clients=' '.join(map(str, trace['blocked_clients'])),
                   eligible_blocks=0, status=trace['status'], fastest=None, rule_extra_seconds=None,
                   rule_extra_pct=None, severe_post_initialization=None, max_largest=None,
                   final_mean_acc=None, final_mean_nmi=None, final_mean_ari=None)
        cells.append(row)
        if trace['status'] != 'captured':
            continue
        for evaluation in trace['quality']:
            for client in evaluation['clients']:
                quality_rows.append(dict(cell=cell, round=evaluation['round'], **client))
        after_start = [x for e in trace['quality'] if e['round'] > 0 for x in e['clients']]
        row.update(severe_post_initialization=sum(x['occupied'] == 1 or x['largest'] >= .99 for x in after_start),
                   max_largest=max(x['largest'] for x in after_start),
                   **{f'final_mean_{k}': mean(x[k] for x in trace['quality'][-1]['clients'])
                      for k in ('acc', 'nmi', 'ari')})
        pairs = [grouped[cell, i] for i in range(1, repeats+1)]
        valid = [g for g in pairs if eligible(g, preset)]
        row['eligible_blocks'] = len(valid)
        for scope, subset in (('all', pairs), ('power_checked', valid)):
            for left, right in (('D', 'B'), ('D', 'E'), ('E', 'B')):
                comparisons.append(dict(cell=cell, scope=scope, left=left, right=right, blocks=len(subset),
                                        **compare(subset, left, right, minimum, wins_needed)))
        if valid:
            costs = {m: mean(seconds(g[m]) for g in valid) for m in METHODS}
            fastest = min(costs, key=costs.get)
            row.update(fastest=fastest, rule_extra_seconds=costs[chosen]-costs[fastest],
                       rule_extra_pct=100*(costs[chosen]/costs[fastest]-1))
        if preset == 'smoke':
            row['status'] = 'smoke'
        elif len(valid) != repeats:
            row['status'] = 'insufficient_paired_timing'
        else:
            if chosen == 'D':
                supported = all(compare(valid, 'D', other, minimum, wins_needed)['passes'] for other in 'BE')
            else:
                supported = not any(compare(valid, other, 'B', minimum, wins_needed)['passes'] for other in 'ED')
            row['status'] = 'supported' if supported else 'not_supported'

    for name, records in [('runs', raw), ('comparisons', comparisons), ('quality', quality_rows), ('cells', cells)]:
        if records:
            write_csv(out/f'{name}.csv', records)
    lines = ['# 三档精确关系生成选路的独立种子确认', '',
             f'模式 {preset}。预设配置 {len(cases)} 个，完成独立重放 {len(runs)} 次。',
             f'逐边核对 {sum(r["comparisons"] for r in raw):,} 次，全部一致。',
             '主要计时为同一教师轨迹上的关系生成，包含路径初始化和缓存构建。'
             '每格的原生聚类质量来自其 B 教师训练的定期检查点。', '',
             '| M | 候选路径 | 配置数 | 支持 | 未支持 | 耗时证据不足 | 初始化受阻 | 严重退化配置 |',
             '|---:|:---:|---:|---:|---:|---:|---:|---:|']
    for size, method in rule.items():
        group = [c for c in cells if c['public_size'] == size]
        counts = [sum(c['status'] == s for c in group)
                  for s in ('supported', 'not_supported', 'insufficient_paired_timing', 'initialization_blocked')]
        severe = sum(bool(c['severe_post_initialization']) for c in group)
        lines.append(f'| {size} | {method} | {len(group)} | ' + ' | '.join(map(str, [*counts, severe])) + ' |')
    if preset == 'smoke':
        lines += ['', '合成短测只覆盖流程。']
    else:
        lines += ['', '4096 档要求 D 对 B 和 E 均达到 3% 且至少赢两块。512 和 16384 档检查 E/D 是否有达到同一门槛的收益。',
                  '逐格判定要求三组有效配对。全计结果保留在 comparisons.csv。',
                  'cells.csv 同时记录固定规则相对事后最快固定路径的额外时间、有效块数和逐格判定。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
