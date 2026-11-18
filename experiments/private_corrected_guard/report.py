"""Per-client quality, stage effects and descriptive resource comparison."""
from pathlib import Path
import numpy as np
from experiments.early_cluster_guard.report import build as detailed_report, _load_runs, _write_csv


def build(out):
    out = Path(out)
    result = detailed_report(out)
    runs = sorted(_load_runs(out), key=lambda r:(r['case']['partition'],r['case']['all_clients'],r['case']['strength']))
    lines = ['# 中心初始化＋全客户端私有校正：全程保护强度探索', '',
        '单seed探索；所有非零保护均持续整个观测期。0档仅做全客户端私有校正。', '',
        'legacy_centers为原中心初始化＋仅0/3校正，逐轮核验历史基线。', '',
        '耗时为描述性结果；通信随轨迹变化。不能将新增学习设置的成本变化当作认证收益。', '',
        '|划分|设置|原生ACC|NMI|最大簇均值|最差客户端最大簇|平均空簇|头部秒|相对legacy耗时|',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|']
    finals, effects, comparisons = [], [], []
    for run in runs:
        case = run['case']; part = case['partition']
        base = next(r for r in runs if r['case']['partition']==part and not r['case']['all_clients'])
        seconds = sum(r['seconds'] for r in run['rows'])
        base_seconds = sum(r['seconds'] for r in base['rows'])
        native = [c['native_head'] for c in run['evaluations'][-1]['clients']]
        mean = {k:float(np.mean([c[k] for c in native])) for k in ('acc','nmi','ari','largest','empty')}
        lines.append(f"|{part}|{case['setting']}|{mean['acc']:.4f}|{mean['nmi']:.4f}|{mean['largest']:.4f}|{max(c['largest'] for c in native):.4f}|{mean['empty']:.2f}|{seconds:.4f}|{seconds/base_seconds:.4f}|")
        base_native = base['evaluations'][-1]['clients']
        for c, m in enumerate(native):
            row = dict(partition=part,setting=case['setting'],strength=case['strength'],client=c,**m)
            finals.append(row)
            comparisons.append(dict(partition=part,setting=case['setting'],client=c,
                acc_change=m['acc']-base_native[c]['native_head']['acc'],
                largest_change=m['largest']-base_native[c]['native_head']['largest'],
                empty_change=m['empty']-base_native[c]['native_head']['empty']))
        events = {(e['round'],e['stage']):e for e in run['diagnostics']}
        for rnd in range(1,run['config']['rounds']+1):
            for start,end,label in (('T0','T1','private'),('T1','T2','public')):
                for a,b in zip(events[rnd,start]['clients'],events[rnd,end]['clients']):
                    effects.append(dict(partition=part,setting=case['setting'],round=rnd,client=a['client'],update=label,
                        largest_change=b['private']['largest']-a['private']['largest'],
                        pseudo_fit_change=b['private']['privatepseudo_fit']-a['private']['privatepseudo_fit'],
                        empty_change=b['private']['empty']-a['private']['empty']))
    _write_csv(out/'final_clients.csv',finals)
    _write_csv(out/'paired_client_changes.csv',comparisons)
    _write_csv(out/'stage_effects.csv',effects)
    (out/'report.md').replace(out/'detailed_report.md')
    # The inherited report is a data formatter; no shutdown occurs in this design.
    detail=(out/'detailed_report.md').read_text(encoding='utf-8')
    detail=detail.replace('Early cluster guard: staircase exploration','Full-duration corrected guard: detailed observations')
    detail=detail.replace('Compare baseline, duration and strength within each partition.','Compare correction-only and full-duration strengths within each partition.')
    detail=detail.replace('Check ALL clients and post-shutdown rebound, not only the 99% threshold.','Check ALL clients, recalls and concentration, not only the 99% threshold. No shutdown is tested.')
    detail=detail.replace('shutdown_checkpoints.csv','selected_checkpoints.csv')
    (out/'detailed_report.md').write_text(detail,encoding='utf-8')
    (out/'shutdown_checkpoints.csv').replace(out/'selected_checkpoints.csv')
    lines += ['', '逐客户端：final_clients.csv；对原中心基线变化：paired_client_changes.csv。',
        '每轮私有/公共段变化：stage_effects.csv；所有召回及分布：diagnostics.csv。',
        '完整检查点及成本：detailed_report.md、test_quality.csv、guard_costs.csv。', '',
        '不自动宣告最佳强度。重点看client1/4，也逐一检查其他客户端的新退化；测试集不要求均匀。',
        '报告末轮及最后50轮状态、空簇和逐伪簇召回；ACC/NMI/ARI作质量护栏，不要求ACC上升。',
        '99%事件只是严重风险标记。没有新增通过阈值，不据单seed宣称普适修复。']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return result
