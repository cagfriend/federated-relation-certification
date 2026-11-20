"""Reports keep generation, complete head time, and common preparation separate."""

import csv
from statistics import mean

from .design import case_id, require, write


def csv_rows(out, filename, rows):
    with (out/filename).open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def run_metrics(r, prep):
    sums = {key: sum(row[key] for row in r['rows']) for key in
            ('seconds', 'private_seconds', 'generation_seconds', 'exchange_seconds', 'public_seconds')}
    phases = {key: sum(row['timing_parts'].get(key, 0.) for row in r['rows']) for key in
              ('compute_seconds', 'aggregation_seconds', 'serialization_seconds')}
    head = r['setup_seconds'] + sums['seconds']
    return dict(**r['case'], head_seconds=head, with_preparation_seconds=head+prep['ae_seconds']+prep['selection_seconds'],
                ae_seconds=prep['ae_seconds'], selection_seconds=prep['selection_seconds'],
                setup_seconds=r['setup_seconds'], **sums,
                first_generation_seconds=r['rows'][0]['generation_seconds'],
                steady_generation_seconds=sum(x['generation_seconds'] for x in r['rows'][1:]),
                teacher_endpoints=sum(sum(x['endpoint_counts']) for x in r['rows']),
                certified_edges=sum(sum(x['certified_edges']) for x in r['rows']),
                **phases, up_bytes=r['traffic'].get('up_bytes', 0), down_bytes=r['traffic'].get('down_bytes', 0),
                cache_bytes=r['cache_bytes'], input_peak_bytes=r['input_peak_bytes'],
                process_peak_bytes=r['process_peak_bytes'], power_plugged_start=r['power_plugged_start'],
                power_plugged_end=r['power_plugged_end'], sleep_seconds_estimate=r.get('sleep_seconds_estimate'))


def build(out, results, preparations, *, smoke):
    metrics, contrasts, pairs, quality, round_data = [], [], [], [], []
    groups, originals = {}, {}
    for r in results:
        cid = case_id(r['case'])
        phases = run_metrics(r, preparations[cid])
        metrics.append(phases)
        group = groups.setdefault(cid, {})
        group.setdefault(r['case']['method'], []).append(phases)
        originals.setdefault(cid, r)
        for row in r['rows']:
            for c, (pts, cert, rate) in enumerate(zip(row['endpoint_counts'], row['certified_edges'],
                                                      row['teacher_positive_rates'])):
                edges = r['cfg']['public_size']//2
                round_data.append(dict(case=cid, method=r['case']['method'], repeat=r['case']['repeat'],
                                       round=row['round'], client=c, endpoints=pts, endpoint_fraction=pts/r['cfg']['public_size'],
                                       certified_edges=cert, certified_fraction=cert/edges, teacher_same_cluster=rate,
                                       teacher_motion=None if row['teacher_motion'] is None else row['teacher_motion'][c],
                                       round_up_bytes=row['traffic_delta'].get('up_bytes', 0),
                                       round_down_bytes=row['traffic_delta'].get('down_bytes', 0)))
    lines = ['# E38 协议下 B/E/D 配对复测', '',
             '本结果为合成数据短测；不执行正式判定。' if smoke else
             '审计与计时轨迹一致；技术重复用于评估同机计时波动，四个配置不是四个独立种子。',
             '', '|配置|相对|完整头部省时|省时（秒）|含准备省时|生成省时|D 更快的块|判定|',
             '|---|---|---:|---:|---:|---:|---:|---|']
    for cid, runs in groups.items():
        data = originals[cid]
        for ev in data['evaluations']:
            for client in ev['clients']:
                q = client['native_head']
                quality.append(dict(case=cid, round=ev['round'], client=client['client'],
                                    **{k: q[k] for k in ('acc', 'nmi', 'ari', 'occupied', 'empty', 'largest')},
                                    severe=q['occupied'] == 1 or q['largest'] >= .99))
        for comparator in ('B', 'E'):
            a, d = runs[comparator], runs['D']
            require(len(a) == (1 if smoke else 3) and len(a) == len(d), 'Wrong number of technical repetitions')
            ratios = []
            for ref, proposed in zip(a, d, strict=True):
                require(ref['repeat'] == proposed['repeat'], 'Timing block mismatch')
                ratio = proposed['head_seconds']/ref['head_seconds']
                ratios.append(ratio)
                pairs.append(dict(case=cid, comparator=comparator, repeat=ref['repeat'],
                                  reference_head_seconds=ref['head_seconds'], D_head_seconds=proposed['head_seconds'],
                                  head_ratio=ratio, head_seconds_saved=ref['head_seconds']-proposed['head_seconds']))
            keys = ('head_seconds', 'with_preparation_seconds', 'generation_seconds')
            ar = {k: mean(r[k] for r in a) for k in keys}
            dr = {k: mean(r[k] for r in d) for k in keys}
            hr, pr, gr = (dr[k]/ar[k] for k in keys)
            saved, wins = ar['head_seconds']-dr['head_seconds'], sum(r < 1. for r in ratios)
            verdict = '短测' if smoke else ('达到门槛' if hr <= .97 and wins >= 2 else '未达到门槛')
            contrasts.append(dict(case=cid, comparator=comparator, head_ratio=hr, head_seconds_saved=saved,
                                  with_prep_ratio=pr, with_prep_seconds_saved=ar['with_preparation_seconds']-dr['with_preparation_seconds'],
                                  generation_ratio=gr, generation_seconds_saved=ar['generation_seconds']-dr['generation_seconds'],
                                  min_block_ratio=min(ratios), max_block_ratio=max(ratios), wins=wins,
                                  blocks=len(ratios), verdict=verdict))
            lines.append(f'|{cid}|D/{comparator}|{1-hr:.2%}|{saved:.6f}|{1-pr:.2%}|{1-gr:.2%}|{wins}/{len(ratios)}|{verdict}|')
    serious = sum(q['severe'] and q['round'] > 0 for q in quality)
    notices = sum(r['power_plugged_start'] is False or r['power_plugged_end'] is False or
                  (r['sleep_seconds_estimate'] or 0.) >= 1. for r in metrics)
    lines.extend(['', f'训练后测试检查点严重事件（逐配置/客户端，不重复计算三方法）：{serious}。',
                  f'端点电源状态或休眠检测提示的运行：{notices}；保留所有原始记录，请结合运行日志审核，未自动剔除。',
                  '', '完整头部 = 初始化 + 实际训练窗口；含准备 = 完整头部 + 本机同配置预训练/快照筛选共用时间。',
                  '峰值为独立进程历史峰值，认证持久数组另列；两者都见 runs.csv。通信是实际应用层字节。',
                  'round_metrics.csv 的上/下行是全客户端轮总量，同一轮在每个客户端行上重复显示，不能沿客户端相加。'])
    for filename, rows in [('runs.csv', metrics), ('paired_blocks.csv', pairs), ('comparisons.csv', contrasts),
                           ('quality.csv', quality), ('round_metrics.csv', round_data)]:
        csv_rows(out, filename, rows)
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    write(out/'summary.json', dict(smoke=smoke, runs=len(results), severe_events=serious, comparisons=contrasts))
