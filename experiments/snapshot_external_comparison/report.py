"""Report quality and time on the declared comparison and ablation axes."""
import csv
from statistics import mean

from .run import EXTERNAL, ON, OFF, STAGES, equivalent, quality, same_pair_rate


def csv_file(out, name, rows):
    if not rows:
        return
    with (out/name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(dict.fromkeys(k for row in rows for k in row)))
        writer.writeheader()
        writer.writerows(rows)


def write_report(out, entries):
    runs, clients, pairs = [], [], []
    lines = [
        '# STL-10 · 最新快照版与外部方法对照',
        '',
        '主表采用统一的私有 KMeans、留出测试集评分流程。Ours 使用头部概率作为 KMeans 输入，外部方法使用编码特征。',
        '测试同簇率是随机抽取两张不同测试图像被分到同簇的概率。Ours 原生头另列，教师同簇边率来自训练协议。',
        '主耗时汇总方法初始化与训练，另列加上 AE 和快照筛选的时间。评估和关系审计均在计时之外。',
        '外部方法与 Ours 的耗时是整套实现和工作量的比较。两个高风险配置来自先前诊断。',
        '',
        '| 种子/划分 | 方法 | ACC | NMI | ARI | 测试同簇率 | 平均/最坏最大簇 | 单簇客户端 | 初始化+训练秒 | 加准备秒 |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|',
    ]
    cases = {}
    for r in entries:
        case = r['case']
        cases.setdefault((case['seed'],case['partition']), {})[(case['method'],case['repeat'])] = r
        label = f"{case['seed']} {case['partition']}"
        if r['status'] != 'completed':
            bad = [p['client'] for p in r['selection'] if p['selected'] is None]
            runs.append(dict(**case, status=r['status'], blocked_clients=','.join(map(str,bad))))
            if case['repeat'] == 1:
                lines.append(f"| {label} | {case['method']} · 初始化受阻 {bad} | — | — | — | — | — | — | — | — |")
            continue
        final = r['evaluations'][-1]['clients']
        q = quality(final)
        native = quality([c['native_head'] for c in final]) if 'native_head' in final[0] else {}
        tail = r['rows'][-40:]
        row = dict(**case, status=r['status'], **q, ae_seconds=r['ae_seconds'], selection_seconds=r['selection_seconds'],
                   setup_seconds=r['setup_seconds'], training_seconds=sum(x['seconds'] for x in r['rows']),
                   method_seconds=r['method_seconds'], with_preparation_seconds=r['with_preparation_seconds'],
                   bytes=r['traffic']['total_bytes'], up_bytes=r['traffic'].get('up_bytes', 0),
                   down_bytes=r['traffic'].get('down_bytes', 0), relation_audits=r['relation_audits'],
                   **{'native_'+k:v for k,v in native.items()},
                   **{k:r['setup_timing'][k]+sum(x['timing'][k] for x in r['rows']) for k in STAGES})
        if native:
            row.update(guard_seconds=sum(x['guard_seconds'] for x in r['rows']),
                       **{k:sum(x[k] for x in r['rows']) for k in ('private_seconds','generation_seconds','exchange_seconds','public_seconds')},
                       aggregate_teacher_tail=mean(x['aggregate_positive_rate'] for x in tail),
                       worst_teacher_tail=max(mean(x['teacher_positive_rates'][c] for x in tail) for c in range(len(final))))
        runs.append(row)
        for e in r['evaluations']:
            for c in e['clients']:
                base = dict(**case, round=e['round'], client=c['client'], method_seconds=e['cumulative_method_seconds'],
                            with_preparation_seconds=e['cumulative_with_prep_seconds'], bytes=e['cumulative_bytes'])
                for mode,row_q in [('common',c)]+([('native',c['native_head'])] if 'native_head' in c else []):
                    clients.append(dict(**base, mode=mode, **{k:row_q[k] for k in ('acc','nmi','ari','largest','occupied','empty')},
                                        same_pair_rate=same_pair_rate(row_q['cluster_counts']),
                                        cluster_counts=' '.join(map(str,row_q['cluster_counts']))))
        if case['repeat']==1 and case['method'] in (*EXTERNAL,ON):
            lines.append(f"| {label} | {case['method']} | {q['acc']:.2%} | {q['nmi']:.4f} | {q['ari']:.4f} |"
                         f" {q['same_pair_rate']:.2%} | {q['largest']:.2%} / {q['worst_largest']:.2%} | {q['single_clients']} |"
                         f" {row['method_seconds']:.3f} | {row['with_preparation_seconds']:.3f} |")
    lines += ['', '## 间隔保护的配对开销与原生簇头质量', '',
              '每个配置做两次技术重复，顺序互换。纯保护秒数为实现内计时，配对差为加入保护后整条训练轨迹的净变化。',
              '原生 ACC 和最大簇均用留出测试集，箭头为权重 0 到 0.5。',
              '', '| 种子/划分 | 净耗时差均值（秒） | 训练净改变量 | 纯保护均值（秒） | 原生 ACC | 原生最坏最大簇 | 末段聚合同簇边率 |',
              '|---|---:|---:|---:|---:|---:|---:|']
    for (seed, part), group in cases.items():
        arms = [group[m,n] for m in (ON,OFF) for n in (1,2)]
        label = f'{seed} {part}'
        if any(r['status']!='completed' for r in arms):
            lines.append(f'| {label} | 初始化受阻 | — | — | — | — | — |')
            continue
        on1,on2,off1,off2 = arms
        if not equivalent(on1,on2) or not equivalent(off1,off2):
            raise ValueError(f'Technical repeat changed the trajectory for {label}')
        if (on1['selected_model_digest'] != off1['selected_model_digest']
                or on1['initial_head_sources'] != off1['initial_head_sources']
                or on1['evaluations'][0]['clients'] != off1['evaluations'][0]['clients']):
            raise ValueError(f'Ablation started with differing models or heads for {label}')
        delta, percents, direct = [], [], []
        for n,(a,b) in enumerate(((on1,off1),(on2,off2)),1):
            time_on = sum(x['seconds'] for x in a['rows'])
            time_off = sum(x['seconds'] for x in b['rows'])
            d = time_on-time_off
            guard = sum(x['guard_seconds'] for x in a['rows'])
            delta.append(d)
            percents.append(d/time_off)
            direct.append(guard)
            pairs.append(dict(seed=seed,partition=part,repeat=n,train_on_seconds=time_on,train_off_seconds=time_off,
                              train_delta_seconds=d,guard_direct_seconds=guard,train_relative_delta=d/time_off,
                              setup_on_seconds=a['setup_seconds'],setup_off_seconds=b['setup_seconds'],
                              selection_on_seconds=a['selection_seconds'],selection_off_seconds=b['selection_seconds']))
        a,b = (quality([c['native_head'] for c in r['evaluations'][-1]['clients']]) for r in (off1,on1))
        t0,t1 = (mean(x['aggregate_positive_rate'] for x in r['rows'][-40:]) for r in (off1,on1))
        lines.append(f"| {label} | {mean(delta):+.4f} | {mean(percents):+.2%} | {mean(direct):.4f} |"
                     f" {a['acc']:.2%} → {b['acc']:.2%} | {a['worst_largest']:.2%} → {b['worst_largest']:.2%} |"
                     f" {t0:.2%} → {t1:.2%} |")
    csv_file(out,'runs.csv',runs)
    csv_file(out,'checkpoints.csv',clients)
    csv_file(out,'guard_pairs.csv',pairs)
    (out/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
