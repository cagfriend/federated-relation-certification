"""Report the observed savings on the live head-training path."""

from collections import defaultdict
from statistics import mean

from experiments.snapshot_certification_timing.design import require
from experiments.snapshot_graph_scaling.design import cell_id

from ..report import eligible, write_csv

STAGES = ('private_seconds', 'generation_seconds', 'exchange_seconds', 'public_seconds')


def measure(r, prep):
    round_seconds = sum(row['seconds'] for row in r['timing'])
    setup = r['setup_seconds']
    head = setup + round_seconds
    parts = {stage: sum(row[stage] for row in r['timing']) for stage in STAGES}
    return dict(head_seconds=head, setup_seconds=setup, **parts,
                training_overhead_seconds=round_seconds-sum(parts.values()),
                with_preparation_seconds=head+prep['ae_seconds']+prep['selection_seconds'],
                ae_seconds=prep['ae_seconds'], selection_seconds=prep['selection_seconds'],
                endpoints=sum(row['endpoints'] for row in r['timing']),
                **{k: r[k] for k in ('cache_bytes','protocol_bytes','input_peak_bytes','process_peak_bytes','suspend_seconds')},
                **{k: r['power'].get(k, 0) for k in ('ac','unknown','battery')},
                up_bytes=r['traffic']['up_bytes'], down_bytes=r['traffic']['down_bytes'])


def summarize(pairs, other, threshold, min_wins):
    metrics = ('generation_seconds', 'head_seconds', 'with_preparation_seconds')
    result = {}
    for k in metrics:
        ref = [a[other][k] for a in pairs]
        d = [a['D'][k] for a in pairs]
        result.update({k+'_saved': mean(ref)-mean(d) if ref else None,
                       k+'_pct': 100*(1-mean(d)/mean(ref)) if ref else None,
                       k+'_wins': sum(x < y for x, y in zip(d, ref, strict=True))})
    result['b_generation_share'] = (mean(g['B']['generation_seconds'] for g in pairs)/
                                    mean(g['B']['head_seconds'] for g in pairs)) if pairs else None
    result['meets_threshold'] = (bool(pairs) and result['head_seconds_pct'] >= 100*threshold and
                                  result['head_seconds_wins'] >= min_wins)
    return result


def report(out, runs, preps, audits, manifest):
    preset = manifest['preset']
    groups = defaultdict(dict)
    for run in runs:
        groups[cell_id(run['case']), run['repeat'], run['attempt']][run['method']] = run
    raw, paired, cells, qualities = [], [], [], []
    first, valid = defaultdict(list), defaultdict(list)
    for (cell, repeat, attempt), group in sorted(groups.items()):
        require(set(group) == set('BED'), f'Unpaired timing {cell} r{repeat} a{attempt}')
        measured = {m: measure(r, preps[cell]) for m, r in group.items()}
        clean = eligible(group, preset)
        for method, summary in measured.items():
            raw.append(dict(cell=cell, method=method, repeat=repeat, attempt=attempt, eligible=clean, **summary))
        for other in 'BE':
            paired.append(dict(cell=cell, repeat=repeat, attempt=attempt, comparator=other, eligible=clean,
                               **summarize([measured], other, manifest['savings_threshold'], manifest['min_wins'])))
        if attempt == 0:
            first[cell].append(measured)
        if clean and (preset == 'full' or attempt == 0):
            valid[cell].append(measured)
    report_rows = []
    needed = 1 if preset == 'smoke' else 3
    for case in manifest['cases']:
        cell = cell_id(case)
        require(len(first[cell]) == needed and len(valid[cell]) <= needed, f'Unexpected block count: {cell}')
        for other in 'BE':
            for scope, pairs in (('original', first[cell]), ('eligible', valid[cell])):
                summary = summarize(pairs, other, manifest['savings_threshold'], manifest['min_wins'])
                status = ('smoke' if preset == 'smoke' else 'incomplete' if len(pairs) != needed
                          else 'passes' if summary['meets_threshold'] else 'below_threshold')
                item = dict(cell=cell, **case, scope=scope, comparator=other, paired_blocks=len(pairs),
                            status=status, **summary)
                cells.append(item)
                if scope == 'eligible':
                    report_rows.append(item)
    for audit in audits:
        for tick in audit['evaluations']:
            for client in tick['clients']:
                qualities.append(dict(cell=cell_id(audit['case']), round=tick['round'], **client))
    for name, data in [('runs', raw), ('paired_blocks', paired), ('comparisons', cells), ('quality', qualities)]:
        write_csv(out/f'{name}.csv', data)
    head = ['# M=4096 完整头部训练确认', '',
            f'通过轨迹对照的独立计时进程 {len(runs)} 个，包含重测。'
            f'非计时审计覆盖 {sum(r["comparisons"] for r in audits)*3:,} 条边，全部一致。', '',
            '| 配置 | 比较 | 有效块 | 生成省时 | 完整头部省时 | 完整头部省秒 | 胜出 | 判定 |',
            '|---|---|---:|---:|---:|---:|---:|---|']
    for row in report_rows:
        def val(k, fmt):
            return format(row[k], fmt) if row[k] is not None else 'NA'
        head.append(f"| {row['cell']} | D/{row['comparator']} | {row['paired_blocks']} | "
                    f"{val('generation_seconds_pct', '+.2f')}% | {val('head_seconds_pct', '+.2f')}% | "
                    f"{val('head_seconds_saved', '+.4f')} | {row['head_seconds_wins']} | {row['status']} |")
    if preset == 'full':
        head += ['', '## 跨种子判定', '',
                 '| 对照 | IID 达标 | 强非 IID 达标 | 完整头部判定 |', '|---|---:|---:|---|']
        for other in 'BE':
            subset = [r for r in report_rows if r['comparator'] == other]
            wins = [sum(r['status'] == 'passes' for r in subset if r['partition'] == p)
                    for p in ('iid','dirichlet_0.1')]
            incomplete = any(r['status'] == 'incomplete' for r in subset)
            verdict = ('证据不足' if incomplete else '达标' if min(wins) >= manifest['seeds_per_partition']
                       else '未达标')
            head.append(f'| D/{other} | {wins[0]}/3 | {wins[1]}/3 | {verdict} |')
    else:
        head += ['', '合成短测用于核验流程。']
    head += ['', '主耗时为头部初始化加各轮实际训练。comparisons.csv 同时给出共同准备口径和 B 的关系生成占比。'
             '含休眠的原始三元组、完整补测与单方法阶段拆分均保留在 runs.csv 和 paired_blocks.csv。']
    (out/'report.md').write_text('\n'.join(head)+'\n', encoding='utf-8')
