"""Descriptive diagnosis reports with explicit teacher/student timing."""
import csv
from pathlib import Path


def write_csv(path, rows, fields=None):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def reports(output, results, anchor):
    output = Path(output)
    clients, stages, rounds = [], [], []
    for arm, record in results.items():
        for checkpoint in record['metrics']:
            for client in checkpoint['clients']:
                clients.append(dict(arm=arm, round=checkpoint['round'], **client))
        for stage in record['stages']:
            for client in stage['clients']:
                for split in ('private', 'public'):
                    stats = client[split]
                    stages.append(dict(arm=arm, round=stage['round'], phase=stage['phase'],
                        client=client['client'], split=split,
                        occupied_clusters=stats['occupied_clusters'],
                        largest_cluster_fraction=stats['largest_cluster_fraction'],
                        pseudo_accuracy=stats.get('pseudo_accuracy'), pseudo_ce=stats.get('pseudo_ce'),
                        mean_confidence=stats['mean_confidence'], cluster_counts=stats['cluster_counts']))
        for row in record['round_records']:
            rounds.append(dict(arm=arm, round=row['round'],
                teacher_positive_fraction=row['positive_relation_fraction'], private_loss=row['private_loss'],
                public_loss=row['public_loss'], public_steps=row['public_optimizer_steps'],
                private_steps=row['private_optimizer_steps'], public_edges=row['public_edges_consumed'],
                student_endpoints=row['student_forward_endpoints']))
    for checkpoint in anchor['metrics']:
        for client in checkpoint['clients']:
            clients.append(dict(arm='historical_public2', round=checkpoint['round'], **client))
    write_csv(output / 'clients.csv', clients)
    write_csv(output / 'stages.csv', stages)
    write_csv(output / 'rounds.csv', rounds)
    fields = ['arm', 'round', 'client', 'single_cluster', 'near_single_cluster', 'largest_cluster_fraction']
    events = [dict(arm=r['arm'], round=r['round'], client=r['client'],
              single_cluster=r['occupied_clusters'] == 1, near_single_cluster=r['largest_cluster_fraction'] >= .99,
              largest_cluster_fraction=r['largest_cluster_fraction']) for r in clients
              if r['occupied_clusters'] == 1 or r['largest_cluster_fraction'] >= .99]
    write_csv(output / 'events.csv', events, fields)
    lines = ['# N12公共更新干预诊断', '',
             '已知失败种子的探索性诊断。历史公共2步记录作为参照。', '',
             '|分支|最终轮次|平均ACC|平均NMI|严格单簇客户端|最大簇≥99%客户端|平均最大簇占比|',
             '|---|---:|---:|---:|---:|---:|---:|']
    for arm in list(results) + ['historical_public2']:
        selected = [r for r in clients if r['arm'] == arm]
        last = max(r['round'] for r in selected)
        final = [r for r in selected if r['round'] == last]
        n = len(final)
        lines.append(f"|{arm}|{last}|{sum(r['acc'] for r in final)/n:.6f}|{sum(r['nmi'] for r in final)/n:.6f}|"
                     f"{sum(r['occupied_clusters']==1 for r in final)}/{n}|{sum(r['largest_cluster_fraction']>=.99 for r in final)}/{n}|"
                     f"{sum(r['largest_cluster_fraction'] for r in final)/n:.6f}|")
    lines += ['', 'clients.csv保留每个测试检查点；stages.csv保留私有及公共探针的阶段状态；events.csv保留所有集中事件。',
              '按完整过程、最终集中度及私有拟合解释结果，再冻结健康种子与新种子确认矩阵。',
              '计时包含诊断探针，private_only保留教师和聚合作为观察。', '']
    (output / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
