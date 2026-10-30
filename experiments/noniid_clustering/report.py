"""Within-seed comparisons and final quality, with common preparation accounting."""
import csv
import json
from pathlib import Path
import statistics as st


def write_csv(path,rows):
    with Path(path).open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def reports(output,cases,profiles):
    rows=[];clients=[]
    for case in cases:
        for name,summary in case['summary'].items():
            latest=summary['final_metrics']
            rows.append(dict(partition=case['partition'],seed=case['seed'],method=name,
                head_pipeline_seconds=summary['head_pipeline_seconds'],
                shared_preparation_plus_head_seconds=summary['shared_preparation_plus_head_seconds'],
                generation_seconds=summary['generation_seconds'],
                refresh_fraction=summary['refresh_fraction'],
                total_bytes=summary['traffic'].get('total_bytes',0),
                persistent_array_bytes=summary['persistent_method_array_bytes'],
                **{k:latest['mean'][k] for k in ('nmi','ari','acc')},
                worst_acc=min(c['acc'] for c in latest['clients']),
                min_occupied_clusters=min(c['occupied_clusters'] for c in latest['clients']),
                max_largest_cluster_fraction=max(c['largest_cluster_fraction'] for c in latest['clients'])))
            clients.extend(dict(partition=case['partition'],seed=case['seed'],method=name,
                                **{k:v for k,v in c.items() if k!='cluster_counts'}) for c in latest['clients'])
    write_csv(output/'summary.csv',rows);write_csv(output/'final_clients.csv',clients)
    paired=[];gains=[]
    for partition in sorted({r['partition'] for r in rows}):
        for baseline in ('B','E'):
            for key in ('generation_seconds','head_pipeline_seconds','shared_preparation_plus_head_seconds','persistent_array_bytes'):
                ratios=[]
                for seed in sorted({r['seed'] for r in rows if r['partition']==partition}):
                    a=next(r for r in rows if (r['partition'],r['seed'],r['method'])==(partition,seed,'D'))
                    b=next(r for r in rows if (r['partition'],r['seed'],r['method'])==(partition,seed,baseline))
                    ratios.append(a[key]/b[key])
                paired.append(dict(partition=partition,comparison='D/'+baseline,metric=key,
                    median_ratio=st.median(ratios),wins=sum(v<1 for v in ratios),seeds=len(ratios)))
        for key in ('nmi','ari','acc','worst_acc'):
            differences=[]
            for seed in sorted({r['seed'] for r in rows if r['partition']==partition}):
                a=next(r for r in rows if (r['partition'],r['seed'],r['method'])==(partition,seed,'B'))
                b=next(r for r in rows if (r['partition'],r['seed'],r['method'])==(partition,seed,'Local'))
                differences.append(a[key]-b[key])
            gains.append(dict(partition=partition,comparison='B-Local',metric=key,
                median_difference=st.median(differences),positive_seeds=sum(v>0 for v in differences),seeds=len(differences)))
    (output/'summary.json').write_text(json.dumps(dict(rows=rows,paired=paired,quality_gains=gains),indent=2),encoding='utf-8')
    if profiles:write_csv(output/'memory_summary.csv',profiles)
    text=['# IID / non-IID异宽聚类实验','',f'已完成{len(cases)}/9组配置-seed；completed.json校验通过才是全部完成。','',
        '|划分|对照|关系生成D/基线|头部训练D/基线|','|---|---|---:|---:|']
    for part in sorted({r['partition'] for r in rows}):
        for base in ('B','E'):
            values=[next(r['median_ratio'] for r in paired if (r['partition'],r['comparison'],r['metric'])==(part,'D/'+base,k))
                    for k in ('generation_seconds','head_pipeline_seconds')]
            text.append('|'+part+'|D/'+base+'|'+'|'.join(f'{v:.5f}' for v in values)+'|')
    text+=['','B-Local最终质量差值（逐seed配对中位数；正数更好）：','',
           '|划分|NMI差|ARI差|ACC差|最差客户端ACC差|','|---|---:|---:|---:|---:|']
    for part in sorted({r['partition'] for r in rows}):
        values=[next(r['median_difference'] for r in gains if (r['partition'],r['metric'])==(part,k)) for k in ('nmi','ari','acc','worst_acc')]
        text.append('|'+part+'|'+'|'.join(f'{v:.6f}' for v in values)+'|')
    text+=['','所有划分各自私有无标签AE预训练与KMeans，然后冻结编码器；真实训练不读取私有真标签。Local仅私有SGD，B/E/D还做公共关系BCE。', '',
        '同配置B/E/D要求每轮参数、关系、接收目标、消息字节和评估一致；不能因此宣称额外通信压缩或协作一定提升质量。', '',
        'shared_preparation_plus_head_seconds给所有方法计入共享最大公共池准备成本；Local也被计入它不需要的公共特征阶段，因此不是Local最小独立成本，不用该列宣称相对Local的速度优势。C0与各准备阶段另存原始case。', '',
        '头部训练时间含初始化/快照/认证/交换/公共SGD，排除oracle与评估；按seed先算比值再取中位数。persistent数组不是进程峰值；可选memory-audit隔离重放，计时不用于性能比较。', '',
        '最终公共测试集相同，报告各客户端结果、最差客户端及簇占用；没有依据缺类客户端强制类别均衡。Dirichlet是经固定样本容量约束的划分，实际直方图见partition.json。', '',
        'smoke仅缩小路径验证，不能作正式质量/性能结论。固定leader0/全员在线，不含真实网络和故障恢复。']
    (output/'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
