import csv
import json
import statistics as st
from pathlib import Path

def csv_write(path, rows):
    if rows:
        with path.open('w', newline='', encoding='utf-8') as f:
            w=csv.DictWriter(f, fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def reports(out, runs, memory_runs, fixture=False):
    out=Path(out); rows=[]; pairs=[]; groups={}
    for meta,r in runs:
        s=r['summary'][meta['method']]; fm=s['final_metrics']['mean']
        row=dict(**meta, head_seconds=s['head_pipeline_seconds'], generation_seconds=s['generation_seconds'],
                 private_seconds=s['private_seconds'], public_seconds=s['public_seconds'],
                 generation_fraction=s['generation_seconds']/s['head_pipeline_seconds'],
                 teacher_recompute_fraction=s['teacher_recompute_fraction'], persistent_bytes=s['persistent_method_array_bytes'],
                 audit_process_peak_bytes=r['process_peak_bytes'], traffic_bytes=s['traffic']['total_bytes'],
                 inherited_base_preparation_seconds=r['common_preparation_seconds'], additional_kmeans_seconds=r['additional_kmeans_seconds'],
                 additional_preparation_seconds=r['additional_preparation_seconds'],
                 cache_loading_seconds=r['shared_loading_seconds'], acc=fm['acc'],nmi=fm['nmi'],ari=fm['ari'])
        rows.append(row);groups.setdefault((meta['partition'],meta['seed'],meta['classes']),{})[meta['method']]=row
    for (part,seed,k),g in sorted(groups.items()):
        for ref in ('B','E'):
            d,b=g['D'],g[ref];shared=d['inherited_base_preparation_seconds']+d['additional_preparation_seconds']
            # Each run has its own measured feature loading cost.
            pairs.append(dict(partition=part,seed=seed,classes=k,comparison='D/'+ref,
                              head_ratio=d['head_seconds']/b['head_seconds'],saved_seconds=b['head_seconds']-d['head_seconds'],
                              generation_ratio=d['generation_seconds']/b['generation_seconds'],
                              with_preparation_ratio=(shared+d['cache_loading_seconds']+d['head_seconds'])/(shared+b['cache_loading_seconds']+b['head_seconds'])))
    summary=[]
    for key in sorted({(p['partition'],p['classes'],p['comparison']) for p in pairs}):
        g=[p for p in pairs if (p['partition'],p['classes'],p['comparison'])==key]
        summary.append(dict(partition=key[0],classes=key[1],comparison=key[2],seeds=len(g),
                            median_head_ratio=st.median(p['head_ratio'] for p in g),min_head_ratio=min(p['head_ratio'] for p in g),
                            max_head_ratio=max(p['head_ratio'] for p in g),wins=sum(p['head_ratio']<1 for p in g),
                            median_saved_seconds=st.median(p['saved_seconds'] for p in g)))
    memory=[]
    for meta,r in memory_runs:
        memory.append(dict(**meta,process_peak_bytes=r['process_peak_bytes'],persistent_bytes=r['summary'][meta['method']]['persistent_method_array_bytes'],
                           note='isolated process, no oracle, no evaluation; includes input verification/loading and interpreter'))
    csv_write(out/'runs.csv',rows);csv_write(out/'paired_cost.csv',pairs);csv_write(out/'paired_summary.csv',summary);csv_write(out/'memory.csv',memory)
    (out/'summary.json').write_text(json.dumps(dict(fixture=fixture,summary=summary,runs=len(runs),memory_runs=len(memory),
           note='K is the output cluster count; ground truth remains 10 classes. Different K changes private targets and training trajectories. No cross-K quality improvement claim.'),ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# K增长的计算与内存边界','', '合成smoke，仅验证实现。' if fixture else '官方STL-10冻结特征；每配置每方法一次，探索性计时。', '',
           'K=10/16/32/64指输出簇数，数据真类数仍是10。跨K会改变伪标签和训练轨迹，不能把跨K差异全部归因于认证维护复杂度。精确性比较只在同K进行。', '',
           '|划分|K|比较|中位头部省时|比值范围|胜出|中位省秒|','|---|---:|---|---:|---|---:|---:|']
    for s in summary:lines.append(f"|{s['partition']}|{s['classes']}|{s['comparison']}|{(1-s['median_head_ratio'])*100:.2f}%|{s['min_head_ratio']:.4f}–{s['max_head_ratio']:.4f}|{s['wins']}/{s['seeds']}|{s['median_saved_seconds']:.3f}|")
    lines+=['','质量指标见runs.csv，仅记录行为。B/E/D同K必须逐轮一致，不要求跨K提高ACC。',
            '内存回放仅覆盖K10/64和一个seed，两划分各B/E/D；不将其外推到中间K或所有seed。memory.csv为空表示未启用--memory-audit。',
            '新增KMeans成本和原始共享准备成本分列；缓存复用不意味着原成本为零。峰值含解释器、输入验证/加载，不是显存或认证临时数组的单独峰值。',
            '旧K10轨迹只作锚点，不混入旧计时。K64仍受uint64上限约束；没有更大K或异构簇数客户端的结论。','']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
