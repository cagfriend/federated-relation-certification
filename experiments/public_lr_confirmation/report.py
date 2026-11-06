import csv
from pathlib import Path
from .design import verdict


def reports(out, cases, records):
    rows, client_rows = [], []
    for case in cases:
        cid = case['case_id']
        baseline = records[cid, 'reference2']['result']
        candidate = records[cid, 'public2_half']['result']
        old = verdict(baseline)
        new = verdict(candidate)
        eligible = old['final_structure'] and old['nmi_floor']
        drop = baseline['metrics'][-1]['mean']['acc'] - candidate['metrics'][-1]['mean']['acc']
        guard = None if not eligible else drop <= .01
        rows.append(dict(**case, **new, acc_guard_applicable=eligible, acc_drop=drop, acc_guard_passed=guard,
                         overall_passed=new['passed'] and guard is not False))
        for arm in ('reference2', 'public2_half'):
            item = records[cid, arm]
            for m in item['result']['metrics']:
                for c in m['clients']:
                    client_rows.append(dict(case_id=cid, arm=arm, origin=item['origin'], round=m['round'], **c))
    for name, data in (('verdicts.csv', rows), ('clients.csv', client_rows)):
        with (Path(out) / name).open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(data[0]))
            writer.writeheader(); writer.writerows(data)
    lines = ['# 公共学习率0.05初步确认', '',
             '每配置单列原0.1参照与0.05候选。历史和新运行的来源见records及clients.csv。', '',
             '|配置|角色|最终结构|过程|NMI地板|适用ACC护栏|总体|',
             '|---|---|---|---|---|---|---|']
    for row in rows:
        lines.append(f"|{row['case_id']}|{row['role']}|{row['final_structure']}|{row['process']}|{row['nmi_floor']}|{row['acc_guard_passed']}|{row['overall_passed']}|")
    lines += ['', '|配置|分支|来源|最终ACC|最终NMI|平均最大簇占比|≥99%客户端|',
              '|---|---|---|---:|---:|---:|---:|']
    for case in cases:
        for arm in ('reference2', 'public2_half'):
            item = records[case['case_id'], arm]
            final = item['result']['metrics'][-1]
            clients = final['clients']
            largest = sum(c['largest_cluster_fraction'] for c in clients) / len(clients)
            near = sum(c['largest_cluster_fraction'] >= .99 for c in clients)
            lines.append(f"|{case['case_id']}|{arm}|{item['origin']}|{final['mean']['acc']:.6f}|{final['mean']['nmi']:.6f}|{largest:.6f}|{near}/{len(clients)}|")
    lines += ['', '过程指标使用20轮起的共同检查点；12轮smoke的过程列仅用于验证数据通路。',
              '新seed1101只有一个随机实例，两个划分单列。历史已知退化配置属于修复范围验证。',
              '原始records保存阶段探针、教师同簇边率、完整簇分布和来源摘要，按完整过程解释每项判定。', '']
    (Path(out) / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
