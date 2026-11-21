"""Report full-graph and exact student-scope comparisons on common blocks."""

from collections import defaultdict
from statistics import mean

from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_graph_scaling.design import cell_id

from ..report import eligible, write_csv

COMPARISONS = (('D','B'), ('D','E'), ('Demand','B'), ('Demand','E'), ('Demand','D'))


def metrics(run):
    stage = {k: sum(row.get(k, 0.) for row in run['timing']) for k in
             ('private_seconds','coordination_seconds','generation_seconds','exchange_seconds','public_seconds')}
    traffic = run['traffic']
    demand_traffic = run.get('traffic_breakdown', {})
    return dict(head_seconds=run['setup_seconds']+sum(row['seconds'] for row in run['timing']),
                setup_seconds=run['setup_seconds'], **stage,
                teacher_path_seconds=stage['coordination_seconds']+stage['generation_seconds']+stage['exchange_seconds'],
                endpoints=sum(row['endpoints'] for row in run['timing']),
                **{k: traffic[k] for k in ('total_bytes','up_bytes','down_bytes','messages')},
                **{k: demand_traffic.get(k, 0) for k in ('request_up_bytes','union_down_bytes','vote_up_bytes',
                                                        'target_down_bytes','ack_bytes','commit_down_bytes')},
                **{k: run[k] for k in ('cache_bytes','protocol_bytes','input_peak_bytes','process_peak_bytes',
                                       'suspend_seconds')},
                **{k: run['power'].get(k, 0) for k in ('ac','unknown','battery')})


def compare(pairs, left, right):
    result = {}
    for field in ('generation_seconds','teacher_path_seconds','head_seconds','up_bytes','down_bytes',
                  'total_bytes','process_peak_bytes'):
        a = [g[left][field] for g in pairs]
        b = [g[right][field] for g in pairs]
        result[f'{field}_saved'] = mean(b)-mean(a) if b else None
        result[f'{field}_saved_pct'] = 100*(1-mean(a)/mean(b)) if b else None
        result[f'{field}_wins'] = sum(x < y for x, y in zip(a, b, strict=True))
    return result


def report(out, runs, audits, manifest):
    grouped = defaultdict(dict)
    for run in runs:
        grouped[cell_id(run['case']), run['repeat'], run['attempt']][run['method']] = run
    originals, chosen = defaultdict(list), defaultdict(list)
    raw, paired, summary, scope = [], [], [], []
    selected = set()
    for (cell, repeat, attempt), group in sorted(grouped.items()):
        require(set(group) == {'B','E','D','Demand'}, f'Incomplete paired run {cell}')
        clean = eligible(group, manifest['preset'])
        primary = clean and (cell, repeat) not in selected
        if primary:
            selected.add((cell, repeat))
        base = dict(cell=cell, repeat=repeat, attempt=attempt, clean=clean, primary=primary)
        values = {m: metrics(r) for m, r in group.items()}
        raw.extend(dict(base, method=m, **v) for m, v in values.items())
        for left, right in COMPARISONS:
            paired.append(dict(base, left=left, right=right, **compare([values], left, right)))
        if attempt == 0:
            originals[cell].append(values)
        if primary:
            chosen[cell].append(values)
    lines = ['# 全图与按需精确训练对照', '',
             f'独立计时 {len(runs)} 次，含补测。全图审计边核对 '
             f'{sum(r["comparisons"] for (_, m), r in audits.items() if m != "Demand"):,} 次，'
             f'Demand 请求边核对 {sum(r["comparisons"] for (_, m), r in audits.items() if m == "Demand"):,} 次。',
             '训练时实际消费的目标、损失及头参数与 B 逐轮相同。', '',
             '| 配置 | 当轮需求边均值 | 当轮需求边占比 |', '|---|---:|---:|']
    for case in manifest['cases']:
        cell = cell_id(case)
        records = audits[cell, 'Demand']['scope']
        full_edges = case['public_size']//2
        edges = mean(r['edges'] for r in records)
        lines.append(f'| {cell} | {edges:.1f} | {edges/full_edges:.2%} |')
        scope.extend(dict(cell=cell, **r, full_edges=full_edges, edge_fraction=r['edges']/full_edges)
                     for r in records)
    lines += ['', '| 配置 | 比较 | 有效块 | 教师计算省时 | 含协调和交换省时 | 完整头部省时 | 完整头部省秒 | 通信字节节省 |',
              '|---|---|---:|---:|---:|---:|---:|---:|']
    required = 3 if manifest['preset'] == 'full' else 1
    for case in manifest['cases']:
        cell = cell_id(case)
        require(len(originals[cell]) == required, 'Original timing matrix is incomplete')
        for left, right in COMPARISONS:
            for name, pairs in (('original', originals[cell]), ('primary', chosen[cell])):
                delta = compare(pairs, left, right)
                status = ('smoke' if manifest['preset'] == 'smoke' else 'incomplete' if len(pairs) != required
                          else 'passes' if delta['head_seconds_saved_pct'] >= manifest['threshold_pct'] and
                          delta['head_seconds_wins'] >= manifest['minimum_wins'] else 'below_threshold')
                summary.append(dict(cell=cell, scope=name, left=left, right=right, blocks=len(pairs),
                                    status=status, **delta))
                if name == 'primary':
                    def fmt(key, suffix=''):
                        v = delta[key]
                        return f'{v:+.2f}{suffix}' if v is not None else 'NA'
                    lines.append(f"| {cell} | {left}/{right} | {len(pairs)} | "
                                 f"{fmt('generation_seconds_saved_pct','%')} | {fmt('teacher_path_seconds_saved_pct','%')} | "
                                 f"{fmt('head_seconds_saved_pct','%')} | {fmt('head_seconds_saved')} | "
                                 f"{fmt('total_bytes_saved_pct','%')} |")
    lines += ['', 'B/E/D 提交完整关系表。Demand 仅提交学生本轮请求的计数。正值表示左侧路径省时或省字节。',
              '配对胜出、逐类消息字节与进程峰值见 comparisons.csv 和 runs.csv。']
    for name, rows in [('runs', raw), ('paired_blocks', paired), ('comparisons', summary), ('demand_scope', scope)]:
        write_csv(out/f'{name}.csv', rows)
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
