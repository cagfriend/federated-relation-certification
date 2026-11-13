"""Paired descriptive resource results with mandatory exactness checks."""
import csv
from pathlib import Path


def report(out, records, memories, smoke):
    by_case = {}
    for case,record in records:
        by_case.setdefault(case['case_id'], {})[case['method']] = record
    rows = []
    for cid, methods in by_case.items():
        base = methods['B']
        for name,r in methods.items():
            s = r['summary'][name]
            b = base['summary']['B']
            row = dict(case_id=cid, method=name,
                       generation_seconds=s['generation_seconds'],
                       head_pipeline_seconds=s['head_pipeline_seconds'],
                       measured_stage_seconds=s['measured_stage_seconds'],
                       generation_saving_vs_B=1-s['generation_seconds']/b['generation_seconds'],
                       head_saving_vs_B=1-s['head_pipeline_seconds']/b['head_pipeline_seconds'],
                       stage_saving_vs_B=1-s['measured_stage_seconds']/b['measured_stage_seconds'],
                       persistent_array_bytes=s['persistent_method_array_bytes'],
                       teacher_recompute_fraction=s['teacher_recompute_fraction'],
                       traffic_equal_B=s['traffic']==b['traffic'],
                       final_acc=s['final_metrics']['mean']['acc'])
            if name == 'D':
                e = methods['E']['summary']['E']
                row.update(head_saving_vs_E=1-s['head_pipeline_seconds']/e['head_pipeline_seconds'],
                           generation_saving_vs_E=1-s['generation_seconds']/e['generation_seconds'],
                           stage_saving_vs_E=1-s['measured_stage_seconds']/e['measured_stage_seconds'])
            rows.append(row)
    fields = list(dict.fromkeys(k for r in rows for k in r))
    with (Path(out)/'comparisons.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w = csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    lines = ['# 私有校正后的认证计算比较', '',
             '合成 smoke 结果，仅用于实现验证。' if smoke else '四个既有环境，每方法独立进程各运行一次。结果为探索性资源测量。', '',
             '| 环境 | D/B生成省时 | D/E生成省时 | D/B完整头部省时 | D/E完整头部省时 | 通信一致 |',
             '|---|---:|---:|---:|---:|---|']
    for row in rows:
        if row['method'] == 'D':
            lines.append(f"| {row['case_id']} | {row['generation_saving_vs_B']:.2%} | "
                         f"{row['generation_saving_vs_E']:.2%} | {row['head_saving_vs_B']:.2%} | "
                         f"{row['head_saving_vs_E']:.2%} | {row['traffic_equal_B']} |")
    lines += ['', '负省时数值表示变慢。阶段和完整头部均包含方法初始化，逐轮 oracle 审计、测试与探针计算在计时外。',
              '完整头部仍包含原框架的轮次管理及快照开销，comparisons.csv另报四阶段相加的耗时。',
              '所有轨迹与已完成的私有校正B逐轮核对。通信比较的是现有协议的序列化消息字节，单机串行耗时未模拟真实并行网络。']
    if memories:
        lines += ['', '## 隔离内存回放', '', '| 环境 | 方法 | 进程峰值字节 | 持久方法数组字节 |', '|---|---|---:|---:|']
        for case,r in memories:
            lines.append(f"| {case['case_id']} | {case['method']} | {r['process_peak_bytes']} | "
                         f"{r['summary'][case['method']]['persistent_method_array_bytes']} |")
        lines += ['', '内存回放关闭 oracle、探针和测试，头部轨迹、教师关系与聚合摘要对齐正式主运行。峰值含运行库和输入加载。其计时不用于省时结论。']
    lines += ['', '本轮各配置每方法一次，无预设省时通过阈值；不将200轮当作独立性能重复。',
              '固定表示与线性头、K10、六端强数量偏斜及当前公共库是受测范围。']
    (Path(out)/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
