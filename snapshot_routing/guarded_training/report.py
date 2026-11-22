"""Summarize paired training cost, trajectory differences and actual ACC."""

from collections import defaultdict
from statistics import mean

from ..report import write_csv
from .worker import STAGES


def metrics(run, process_seconds):
    rows = run['rows']
    stages = {key: sum(row[key] for row in rows) for key in STAGES}
    return dict(
        head_seconds=run['setup_seconds'] + sum(row['seconds'] for row in rows),
        setup_seconds=run['setup_seconds'], **stages, worker_seconds=run['worker_seconds'],
        process_seconds=process_seconds, load_seconds=run['load_seconds'],
        evaluation_seconds=run['evaluation_seconds'], shared_ae_seconds=run['shared_ae_seconds'],
        selection_seconds=run['selection_seconds'], cache_bytes=run['cache_bytes'],
        endpoints=sum(row['endpoints'] for row in rows), final_acc=mean(c['acc'] for c in run['quality'][-1]['clients']),
        scale_fallbacks=run['triggers'].get('scale', 0), rebuilds=run['triggers'].get('rebuild', 0),
        suspend_seconds=run['suspend_seconds'], **{k: run['power'].get(k, 0) for k in ('ac', 'battery', 'unknown')},
    )


def delta_percent(pairs, item):
    return 100*(sum(row[f'C_{item}'] for row in pairs)/sum(row[f'D_{item}'] for row in pairs)-1) if pairs else None


def report(out, manifest, pairs):
    results, processes, quality, trajectory = [], [], [], []
    grouped = defaultdict(list)
    for pair, group in pairs:
        slot = {key: pair[key] for key in ('cell', 'repeat', 'order', 'attempt', 'eligible')}
        values = {method: metrics(run, pair['process_seconds'][method]) for method, run in group.items()}
        for method, stats in values.items():
            processes.append(dict(**slot, method=method, **stats))
            for checkpoint in group[method]['quality']:
                quality.extend(dict(**slot, method=method, round=checkpoint['round'], **client)
                               for client in checkpoint['clients'])
        diffs = []
        for d, c in zip(group['D']['rows'], group['C']['rows'], strict=True):
            changed = sum((int(x, 16) ^ int(y, 16)).bit_count()
                          for x, y in zip(d['relations'], c['relations'], strict=True))
            diffs.append(dict(**slot, round=d['round'], edge_differences=changed, head_equal=d['head'] == c['head'],
                              traffic_equal=d['traffic'] == c['traffic']))
        trajectory.extend(diffs)
        last_d, last_c = (group[m]['quality'][-1]['clients'] for m in 'DC')
        acc_deltas = [100*(c['acc']-d['acc']) for d,c in zip(last_d,last_c,strict=True)]
        result = dict(**slot,
                      **{f'{m}_{key}': values[m][key] for m in 'DC' for key in
                         ('head_seconds', 'process_seconds', 'generation_seconds', 'final_acc')},
                      final_acc_delta_pp=mean(acc_deltas), worst_client_acc_delta_pp=min(acc_deltas),
                      max_client_abs_acc_delta_pp=max(map(abs, acc_deltas)),
                      total_edge_differences=sum(row['edge_differences'] for row in diffs),
                      first_relation_difference=next((row['round'] for row in diffs if row['edge_differences']), None),
                      first_head_difference=next((row['round'] for row in diffs if not row['head_equal']), None),
                      scale_fallbacks=values['C']['scale_fallbacks'], rebuilds=values['C']['rebuilds'])
        for key in ('head_seconds', 'process_seconds', 'generation_seconds'):
            result[f'{key}_delta'] = result[f'C_{key}'] - result[f'D_{key}']
            result[f'{key}_delta_pct'] = delta_percent([result], key)
        results.append(result)
        grouped[pair['cell']].append(result)

    summary = []
    for cell, entry in manifest['references'].items():
        all_rows = grouped[cell]
        timing = [r for r in all_rows if r['eligible']]
        # Each technical repeat contributes one original ACC observation,
        # regardless of whether the pair's timing was eligible.
        first = [r for r in all_rows if r['attempt'] == 0]
        summary.append(dict(
            cell=cell, **entry['case'], rounds=entry['rounds'], eligible_pairs=len(timing), planned_pairs=len(first),
            D_head_seconds=mean(r['D_head_seconds'] for r in timing) if timing else None,
            C_head_seconds=mean(r['C_head_seconds'] for r in timing) if timing else None,
            head_delta_s=mean(r['head_seconds_delta'] for r in timing) if timing else None,
            head_delta_pct=delta_percent(timing, 'head_seconds'),
            head_C_slower=sum(r['head_seconds_delta'] > 0 for r in timing),
            process_delta_pct=delta_percent(timing, 'process_seconds'),
            generation_delta_pct=delta_percent(timing, 'generation_seconds'),
            D_final_acc_pct=100*mean(r['D_final_acc'] for r in first),
            C_final_acc_pct=100*mean(r['C_final_acc'] for r in first),
            acc_delta_pp=mean(r['final_acc_delta_pp'] for r in first),
            worst_client_acc_delta_pp=min(r['worst_client_acc_delta_pp'] for r in first),
            max_client_abs_acc_delta_pp=max(r['max_client_abs_acc_delta_pp'] for r in first),
            relation_difference_pairs=sum(r['total_edge_differences'] > 0 for r in first),
            head_difference_pairs=sum(r['first_head_difference'] is not None for r in first),
            scale_fallbacks=max(r['scale_fallbacks'] for r in first),
            rebuilds=max(r['rebuilds'] for r in first),
        ))

    def fmt(value, spec):
        return '—' if value is None else format(value, spec)

    lines = ['# 当前 D 与合并版的完整头部训练对照', '',
             '合并版减当前 D。时间差为正表示合并版用时较长。ACC 均以六客户端等权平均计算。',
             '', '| 配置 | 轮数 | 合格配对 | D 头部秒 | 合并版头部秒 | 头部差 % | 进程墙钟差 % | '
             'D 最终 ACC % | 合并版最终 ACC % | ACC 差百分点 | 有关系差异的原始配对 |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for row in summary:
        lines.append(f"| {row['cell']} | {row['rounds']} | {row['eligible_pairs']}/{row['planned_pairs']} | "
                     f"{fmt(row['D_head_seconds'], '.4f')} | {fmt(row['C_head_seconds'], '.4f')} | "
                     f"{fmt(row['head_delta_pct'], '+.2f')} | {fmt(row['process_delta_pct'], '+.2f')} | "
                     f"{row['D_final_acc_pct']:.3f} | {row['C_final_acc_pct']:.3f} | {row['acc_delta_pp']:+.3f} | "
                     f"{row['relation_difference_pairs']}/{row['planned_pairs']} |")
    lines.extend(['', '完整头部时间含头初始化、固定特征提取和全部训练轮。'
                  '进程墙钟含启动、加载、测试评估、审计及写盘。冻结编码器的共同预训练耗时另记。'
                  '配对和逐阶段值见 paired.csv 与 runs.csv，逐客户端 ACC 曲线见 quality.csv。'
                  'trajectory.csv 保存逐轮的边差异数以及头参数和通信一致性。'])
    if manifest['preset'] != 'full':
        lines.extend(['', '本表为短测，用于检查运行和统计流程。'])
    elif any(r['eligible_pairs'] != r['planned_pairs'] for r in summary):
        lines.extend(['', '部分配置的有效计时配对不足。原始配对完整保留在 paired.csv。'])
    paths = []
    for name, rows in (('cells', summary), ('paired', results), ('runs', processes), ('quality', quality),
                       ('trajectory', trajectory)):
        path = out/f'{name}.csv'
        write_csv(path, rows)
        paths.append(path)
    path = out/'report.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return [*paths, path]
