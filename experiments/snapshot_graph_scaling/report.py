"""Resolve break-even by size and comparator, with explicit power diagnostics."""

from statistics import mean

from experiments.snapshot_certification_timing.design import require, write
from experiments.snapshot_certification_timing.report import csv_rows
from .design import cell_id, context_id


def metrics(r, prep):
    rows, case = r['rows'], r['case']
    traffic = r['traffic']
    sums = {k: sum(row[k] for row in rows) for k in
            ('seconds', 'generation_seconds', 'private_seconds', 'exchange_seconds', 'public_seconds')}
    head = r['setup_seconds'] + sums['seconds']
    power = r['power']
    sleep = r['sleep_seconds_estimate']
    return dict(cell=cell_id(case), **case, head_seconds=head, setup_seconds=r['setup_seconds'], **sums,
                with_preparation_seconds=head+prep['ae_seconds']+prep['selection_seconds'],
                ae_seconds=prep['ae_seconds'], snapshot_seconds=prep['selection_seconds'],
                first_generation_seconds=rows[0]['generation_seconds'],
                steady_generation_seconds=sum(row['generation_seconds'] for row in rows[1:]),
                endpoints=sum(sum(row['endpoint_counts']) for row in rows),
                certified_edges=sum(sum(row['certified_edges']) for row in rows),
                student_edges=sum(sum(row['student_edges']) for row in rows),
                up_bytes=traffic['up_bytes'], down_bytes=traffic['down_bytes'],
                cache_bytes=r['cache_bytes'], protocol_bytes=r['protocol_bytes'],
                input_peak_bytes=r['input_peak_bytes'], process_peak_bytes=r['process_peak_bytes'],
                ac_samples=power.get('ac', 0), battery_samples=power.get('battery', 0),
                unknown_power_samples=power.get('unknown', 0), sleep_seconds_estimate=sleep,
                monitored_ac=(set(power) == {'ac'} and sleep is not None and sleep < 1.))


def build(out, results, prep, *, smoke):
    runs, quality, rounds, paired, summary = [], [], [], [], []
    cells = {}
    for r in results:
        case = r['case']
        rec = metrics(r, prep[context_id(case)])
        runs.append(rec)
        cid = cell_id(case)
        cells.setdefault(cid, {}).setdefault(case['method'], []).append(rec)
        for row in r['rows']:
            rounds.append(dict(cell=cid, method=case['method'], repeat=case['repeat'], round=row['round'],
                               generation_seconds=row['generation_seconds'], head_round_seconds=row['seconds'],
                               student_edges=sum(row['student_edges']), endpoints=sum(row['endpoint_counts']),
                               certified_edges=sum(row['certified_edges']),
                               mean_teacher_motion=None if row['teacher_motion'] is None else mean(row['teacher_motion']),
                               teacher_same_cluster=mean(row['teacher_positive_rates']),
                               up_bytes=row['traffic_delta'].get('up_bytes',0),
                               down_bytes=row['traffic_delta'].get('down_bytes',0)))
        if case['method'] == 'B' and case['repeat'] == 1:
            for ev in r['evaluations']:
                for row in ev['clients']:
                    native = row['native_head']
                    quality.append(dict(cell=cid, round=ev['round'], client=row['client'],
                                        **{k: native[k] for k in ('acc','nmi','ari','largest','occupied','empty')},
                                        severe=native['occupied'] == 1 or native['largest'] >= .99))
    lines = ['# E38 公共图规模对照', '',
             '合成短测，数值不用于性能结论。' if smoke else
             '各规模分别核对 B/E/D 的精确轨迹；按配置、规模和基线独立判读。',
             '', '|配置|相对|关系生成省时（胜出）|完整头部省时（胜出）|含准备省时|插电完整块|主判定|',
             '|---|---|---:|---:|---:|---:|---|']
    keys = ('generation_seconds','head_seconds','with_preparation_seconds')
    for cid, group in sorted(cells.items(), key=lambda item: (context_id(item[1]['B'][0]), item[1]['B'][0]['public_size'])):
        d = sorted(group['D'], key=lambda x: x['repeat'])
        by_repeat = {m: {r['repeat']: r for r in g} for m, g in group.items()}
        clean = {r['repeat'] for r in d if all(by_repeat[m][r['repeat']]['monitored_ac'] for m in 'BED')}
        for method in ('B', 'E'):
            ref = sorted(group[method], key=lambda x: x['repeat'])
            require([r['repeat'] for r in d] == [r['repeat'] for r in ref] == list(range(1, 2 if smoke else 4)),
                    'Incomplete technical repeats')
            records = []
            for a, b in zip(ref, d, strict=True):
                repeat = a['repeat']
                item = dict(cell=cid, comparator=method, repeat=repeat, monitored_ac=repeat in clean,
                            **{f'{k}_ratio': b[k]/a[k] for k in keys})
                records.append(item)
                paired.append(item)
            means = {f'{k}_ratio': mean(x[k] for x in d)/mean(x[k] for x in ref) for k in keys}
            wins = {f'{k}_wins': sum(x[f'{k}_ratio'] < 1. for x in records) for k in keys}
            saved = {k: mean(x[k] for x in ref)-mean(x[k] for x in d) for k in keys}
            hr, gr = means['head_seconds_ratio'], means['generation_seconds_ratio']
            hw, gw = wins['head_seconds_wins'], wins['generation_seconds_wins']
            n = len(d)
            nominal = not smoke and hr <= .97 and hw >= 2
            gen_nominal = not smoke and gr <= .97 and gw >= 2
            verdict = ('短测' if smoke else '达到门槛' if nominal and len(clean) == 3 else
                       '全计达门槛，供电/休眠待复核' if nominal else '未达到门槛')
            selected = lambda g: [x['head_seconds'] for x in g if x['repeat'] in clean]
            clean_ratio = mean(selected(d))/mean(selected(ref)) if clean else None
            summary.append(dict(cell=cid, comparator=method, public_size=d[0]['public_size'], blocks=n,
                                **means, **wins, head_seconds_saved=saved['head_seconds'],
                                generation_seconds_saved=saved['generation_seconds'], ac_blocks=len(clean),
                                context=context_id(d[0]), generation_meets_rule=gen_nominal,
                                head_meets_rule=nominal,
                                ac_head_ratio=clean_ratio, min_block_head_ratio=min(x['head_seconds_ratio'] for x in records),
                                max_block_head_ratio=max(x['head_seconds_ratio'] for x in records), verdict=verdict))
            lines.append(f"|{cid}|D/{method}|{1-gr:+.2%}（{gw}/{n}）|{1-hr:+.2%}（{hw}/{n}）|"
                         f"{1-means['with_preparation_seconds_ratio']:+.2%}|{len(clean)}/{n}|{verdict}|")
    crossover = []
    for context in sorted({r['context'] for r in summary}):
        for method in ('B', 'E'):
            rows = [r for r in summary if r['context'] == context and r['comparator'] == method]
            found = {}
            for k in ('generation', 'head'):
                found[f'first_{k}_all'] = min((r['public_size'] for r in rows if r[f'{k}_meets_rule']), default=None)
                found[f'first_{k}_monitored_ac'] = min((r['public_size'] for r in rows if r[f'{k}_meets_rule']
                                                        and r['ac_blocks'] == r['blocks']), default=None)
            crossover.append(dict(context=context, comparator=method, **found))
    if not smoke:
        lines.extend(['', '首次达到门槛的实测规模（空值见 CSV；只定位本网格，不能外推阈值）。',
                      '', '|配置|相对|全计：生成 / 头部|插电监测完整：生成 / 头部|',
                      '|---|---|---|---|'])
        for r in crossover:
            def shown(k):
                return r[k] or '—'
            lines.append(f"|{r['context']}|D/{r['comparator']}|{shown('first_generation_all')} / {shown('first_head_all')}|"
                         f"{shown('first_generation_monitored_ac')} / {shown('first_head_monitored_ac')}|")
    events = sum(row['severe'] and row['round'] > 0 for row in quality)
    lines.extend(['', f'训练后严重集中事件：{events}。逐客户端检查点见 quality.csv。',
                  '“插电完整块”要求三方法的采样点均显示插电，且无可检测的 ≥1 秒休眠；无法读取时保留为未知。主表保留所有原始结果。',
                  '生成时间含首轮；完整头部含初始化与训练，不含数据载入、额外审计及评估；含准备另加上一次实验测得并复用的 E38 AE 和快照选择成本。'])
    for filename, data in [('runs.csv',runs),('quality.csv',quality),('round_metrics.csv',rounds),
                           ('paired_blocks.csv',paired),('comparisons.csv',summary),('crossover.csv',crossover)]:
        csv_rows(out, filename, data)
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    write(out/'summary.json', dict(smoke=smoke, runs=len(results), severe_events=events, comparisons=summary))
