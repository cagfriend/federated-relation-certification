"""Per-case report for the paired P2 timing repetitions."""
import json
import statistics
from pathlib import Path

from experiments.lr_compute.report import _write
from .design import METHODS, REPEATS, criteria


def _ratio(a, b):
    return a / b if a is not None and b not in (None, 0) else None


def _need(ok, message):
    if not ok:
        raise ValueError(message)


def reports(out, completed, fixture=False):
    out = Path(out)
    runs, groups = [], {}
    required_meta = {'case_id','family','seed','partition','role','method','repeat','position'}
    for meta, r in completed:
        _need(required_meta <= set(meta), 'Incomplete P2 metadata')
        m, rep, cid = meta['method'], meta['repeat'], meta['case_id']
        _need(m in METHODS and type(rep) is int and rep in range(REPEATS), 'Invalid method/repeat')
        _need(r.get('method') == m and r.get('repeat') == rep and r.get('position') == meta['position'], 'Run identity mismatch')
        s = r['summary'][m]
        phases = {f'{p}_seconds': s[f'{p}_seconds'] for p in ('private','generation','exchange','public')}
        traffic = s['traffic']
        prep = r['preparation']
        row = dict(**meta, head_pipeline_seconds=s['head_pipeline_seconds'], **phases,
            generation_fraction=s['generation_fraction'], serialized_traffic_bytes=traffic['total_bytes'],
            process_peak_bytes=r['process_peak_bytes'], persistent_method_array_bytes=s['persistent_method_array_bytes'],
            base_preparation_seconds=prep['base_seconds'], additional_preparation_seconds_raw=prep['additional_seconds_raw'],
            additional_preparation_seconds=prep['additional_seconds'], total_with_shared_preparation_seconds=s['with_shared_preparation_seconds'],
            known_preparation_contamination=prep['known_contamination'], preparation_reason=prep['reason'],
            final_acc=s['final_metrics']['mean']['acc'], final_nmi=s['final_metrics']['mean']['nmi'], final_ari=s['final_metrics']['mean']['ari'])
        row.update({'traffic_'+k:v for k,v in traffic.items() if k != 'total_bytes'})
        runs.append(row)
        slot = groups.setdefault(cid, {'meta':meta, 'reps':{}})['reps'].setdefault(rep,{})
        _need(m not in slot, 'Duplicate method in case/repeat')
        slot[m] = (meta,r,row)

    paired, summaries, criteriarows, checkpoints = [], [], [], []
    for cid, group in sorted(groups.items()):
        _need(set(group['reps']) == set(range(REPEATS)), 'Need exactly three repeats: '+cid)
        for rep, triple in group['reps'].items():
            _need(set(triple) == set(METHODS), 'Incomplete method triple: '+cid)
        meta = group['meta']; method_data = {m:[] for m in METHODS}
        rb, re = [], []
        for rep in range(REPEATS):
            t = group['reps'][rep]
            b,d,e=(t[x][2] for x in ('B','D','E'))
            rb.append(_ratio(d['head_pipeline_seconds'],b['head_pipeline_seconds']))
            re.append(_ratio(d['head_pipeline_seconds'],e['head_pipeline_seconds']))
            for m in METHODS: method_data[m].append(t[m][2]['head_pipeline_seconds'])
            paired.append(dict(case_id=cid,family=meta['family'],seed=meta['seed'],partition=meta['partition'],role=meta['role'],repeat=rep,
                D_B_head_ratio=rb[-1],D_B_saving_seconds=b['head_pipeline_seconds']-d['head_pipeline_seconds'],
                D_B_saving_fraction=1-rb[-1] if rb[-1] is not None else None,
                D_E_head_ratio=re[-1],D_E_saving_seconds=e['head_pipeline_seconds']-d['head_pipeline_seconds'],
                D_E_saving_fraction=1-re[-1] if re[-1] is not None else None,
                generation_ratio_D_B=_ratio(d['generation_seconds'],b['generation_seconds']),
                generation_ratio_D_E=_ratio(d['generation_seconds'],e['generation_seconds']),
                preparation_ratio_D_B=_ratio(d['total_with_shared_preparation_seconds'],b['total_with_shared_preparation_seconds']),
                preparation_ratio_D_E=_ratio(d['total_with_shared_preparation_seconds'],e['total_with_shared_preparation_seconds'])))
        crit=criteria(rb,re)
        criteria_row=dict(case_id=cid,family=meta['family'],seed=meta['seed'],partition=meta['partition'],role=meta['role'],**crit,
            C1_median_D_B_saving_percent=100*(1-statistics.median(rb)),C2_median_D_E_saving_percent=100*(1-statistics.median(re)),
            D_B_wins=sum(x<1 for x in rb),D_E_wins=sum(x<1 for x in re),threshold_C1_percent=10,threshold_C2_percent=3,required_wins=2)
        criteriarows.append(criteria_row)
        means={m:statistics.mean(v) for m,v in method_data.items()}
        summaries.append(dict(case_id=cid,family=meta['family'],seed=meta['seed'],partition=meta['partition'],role=meta['role'],
            **{m+'_mean_head_seconds':means[m] for m in METHODS},mean_D_B_ratio=_ratio(means['D'],means['B']),mean_D_E_ratio=_ratio(means['D'],means['E']),
            D_B_median_ratio=statistics.median(rb),D_B_min_ratio=min(rb),D_B_max_ratio=max(rb),D_E_median_ratio=statistics.median(re),D_E_min_ratio=min(re),D_E_max_ratio=max(re),
            D_B_wins=criteria_row['D_B_wins'],D_E_wins=criteria_row['D_E_wins'],D_B_median_saving_seconds=statistics.median([x['D_B_saving_seconds'] for x in paired if x['case_id']==cid]),
            D_E_median_saving_seconds=statistics.median([x['D_E_saving_seconds'] for x in paired if x['case_id']==cid]),
            B_relative_range=(max(method_data['B'])-min(method_data['B']))/means['B'],E_relative_range=(max(method_data['E'])-min(method_data['E']))/means['E'],D_relative_range=(max(method_data['D'])-min(method_data['D']))/means['D'],**crit))
        # Shared quality trajectory is represented once: B, first technical repeat.
        bm, br, _ = group['reps'][0]['B']
        for cp in br['metrics']:
            for c in cp['clients']:
                checkpoints.append(dict(case_id=cid,family=meta['family'],seed=meta['seed'],partition=meta['partition'],role=meta['role'],baseline='B',repeat=0,round=cp['round'],client=c['client'],width=c['width'],acc=c['acc'],nmi=c['nmi'],ari=c['ari'],occupied_clusters=c['occupied_clusters'],largest_cluster_fraction=c['largest_cluster_fraction']))
    _write(out/'runs.csv',runs); _write(out/'paired_repeats.csv',paired); _write(out/'case_summary.csv',summaries)
    _write(out/'criteria.csv',criteriarows); _write(out/'checkpoints.csv',checkpoints)
    summary=dict(fixture=fixture,runs=len(runs),cases=len(groups),paired_repeats=len(paired),criteria_cases=len(criteriarows),quality_trajectories=len(groups))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# P2 LR .05 重复测量报告','','技术重复：%d 个运行，%d 个案例。每个案例按重复编号配对 B、E、D。时间结果仅作本地探索性测量；技术重复不是独立种子证据。'%(len(runs),len(groups)), '',
      '## 逐案例冻结判据','','| 案例 | 角色 | C1 中位 D/B 节省 | C2 中位 D/E 节省 | D/B 胜场 | D/E 胜场 | C1 | C2 | C3 | 通过 |','|---|---|---:|---:|---:|---:|---|---|---|---|']
    for x in criteriarows: lines.append(f"| {x['case_id']} | {x['role']} | {x['C1_median_D_B_saving_percent']:.2f}% | {x['C2_median_D_E_saving_percent']:.2f}% | {x['D_B_wins']}/3 | {x['D_E_wins']}/3 | {x['C1']} | {x['C2']} | {x['C3']} | {x['passed']} |")
    lines += ['', 'C1/C2/C3 均按单案例判定，不合并案例或种子。C1 要求中位 D/B 节省至少 10%；C2 要求中位 D/E 节省至少 3%；C3 要求两组比较各至少 2/3 次获胜。','', '准备时间包含已知污染的案例保留 NA；原始准备字段保存在 runs.csv，未以零替代。准备时间合计不是本表统计对象。checkpoints.csv 仅含 B 的首个技术重复共享质量轨迹。', '']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return summary
