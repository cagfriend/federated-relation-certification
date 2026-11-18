"""Disaggregate the paired comparison by client, checkpoint, and phase."""
import csv
from statistics import mean


def zero_recall(p):
    return sum(r == 0 for r in p['pseudo_recall'] if r is not None)


def write_csv(path, rows):
    with path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build(out, pairs, cfg):
    checkpoints, stages, late, recall = [], [], [], []
    lines = ['# 公共更新开关：配对定位', '',
             '差值定义：关闭 − 开启。旧公共开启轨迹来自同一个种子；逐轮记录用于描述，不是独立重复。',
             '关闭分支的教师正边比例是只读投影；没有提交目标及通信。ACC/NMI/ARI 作为质量护栏。', '',
             '|划分|保护|客户端|末轮测试最大簇 开→关|末轮私有零召回伪簇 开→关|末轮私有拟合 开→关|',
             '|---|---:|---:|---:|---:|---:|']
    severe = []
    for case, on, off in pairs:
        base = dict(partition=case['partition'], strength=case['strength'])
        for mode, result in (('on', on), ('off', off)):
            for ev in result['evaluations']:
                for row in ev['clients']:
                    c, h = row['client'], row['native_head']
                    hit = h['occupied'] == 1 or h['largest'] >= .99
                    checkpoints.append(dict(**base, mode=mode, round=ev['round'], client=c,
                                            acc=h['acc'], nmi=h['nmi'], ari=h['ari'], largest=h['largest'],
                                            occupied=h['occupied'], empty=h['empty'], severe=hit,
                                            cluster_counts=' '.join(map(str, h['cluster_counts']))))
                    if hit and ev['round']:
                        severe.append((mode, case['partition'], case['strength'], ev['round'], c))
            for obs in result['diagnostics']:
                for c, row in enumerate(obs['clients']):
                    p = row['private']
                    rates = obs['teacher_positive_rates']
                    indexes = dict(**base, mode=mode, round=obs['round'], stage=obs['stage'], client=c)
                    stages.append(dict(**indexes, private_largest=p['largest'], private_empty=p['empty'],
                                       pseudo_fit=p['privatepseudo_fit'], zero_recall=zero_recall(p),
                                       public_largest=row['public']['largest'], teacher_positive_rate=rates[c] if rates else None))
                    recall.extend(dict(**indexes, pseudo_cluster=k, recall=v,
                                       support=result.get('centers_and_labels', result.get('initial_checks'))[c]['pseudo_histogram'][k])
                                  for k, v in enumerate(p['pseudo_recall']))
        for c in range(len(cfg['capacities'])):
            on_test, off_test = (r['evaluations'][-1]['clients'][c]['native_head'] for r in (on, off))
            on_private, off_private = (r['diagnostics'][-1]['clients'][c]['private'] for r in (on, off))
            n = cfg['rounds']
            window = range(max(1, n-49), n+1)
            def private(r, i, stride, stage):
                idx = 1 + stride*(i-1) + stage
                return r['diagnostics'][idx]['clients'][c]['private']
            def t1_teacher(r, i, stride):
                return r['diagnostics'][2 + stride*(i-1)]['teacher_positive_rates'][c]
            changes = {}
            for metric, key in (('largest', 'largest'), ('fit', 'privatepseudo_fit')):
                for mode, r, stride in (('on', on, 3), ('off', off, 2)):
                    changes[f'{mode}_private_delta_{metric}'] = mean(private(r, i, stride, 1)[key] -
                                                                   private(r, i, stride, 0)[key] for i in window)
                changes[f'on_public_delta_{metric}'] = mean(private(on, i, 3, 2)[key] -
                                                            private(on, i, 3, 1)[key] for i in window)
            late.append(dict(**base, client=c, rounds=len(window), **changes,
                             on_teacher_rate=mean(t1_teacher(on, i, 3) for i in window),
                             off_projected_teacher_rate=mean(t1_teacher(off, i, 2) for i in window),
                             final_test_largest_delta=off_test['largest']-on_test['largest'],
                             final_zero_recall_delta=zero_recall(off_private)-zero_recall(on_private),
                             final_native_acc_delta=off_test['acc']-on_test['acc'],
                             final_native_nmi_delta=off_test['nmi']-on_test['nmi'],
                             final_native_ari_delta=off_test['ari']-on_test['ari']))
            lines.append(f"|{case['partition']}|{case['strength']:g}|{c}|{on_test['largest']:.1%} → {off_test['largest']:.1%}|"
                         f"{zero_recall(on_private)} → {zero_recall(off_private)}|"
                         f"{on_private['privatepseudo_fit']:.1%} → {off_private['privatepseudo_fit']:.1%}|")
    lines += ['', f'严重事件（从首个训练后测试点起，单簇或最大簇≥99%）：开 {sum(x[0] == "on" for x in severe)}，'
                   f'关 {sum(x[0] == "off" for x in severe)}。逐事件见 `checkpoints.csv`。', '',
              '逐轮见 `stages.csv`；小伪簇的支持数和召回见 `pseudo_recall.csv`；末50轮阶段变化及测试差值见 `late_pairs.csv`。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    for key, rows in (('checkpoints', checkpoints), ('stages', stages), ('late_pairs', late), ('pseudo_recall', recall)):
        write_csv(out/f'{key}.csv', rows)
