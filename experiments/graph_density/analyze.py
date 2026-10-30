"""Analyze completed graph runs without modifying original case files."""
import argparse
import csv
import json
from pathlib import Path
import statistics as st

from experiments.public_scaling.config import from_json
from experiments.public_scaling.data import sha
from experiments.public_scaling.run import checked_case, check_shared_cases, validate_environment
from experiments.public_scaling.util import load_json


def paired(cases, ref, field):
    ratios = [c['summary']['D'][field] / c['summary'][ref][field] for c in cases]
    savings = [c['summary'][ref][field] - c['summary']['D'][field] for c in cases]
    return dict(percent_less=100 * (1-st.median(ratios)), seconds_saved=st.median(savings),
                ratio_range=[min(ratios), max(ratios)], wins=sum(r < 1 for r in ratios),
                raw_pairs=[dict(seed=c['seed'], ratio=r, seconds_saved=s) for c,r,s in zip(cases,ratios,savings)])


def analyze(output):
    output = Path(output)
    done, env = load_json(output / 'completed.json'), load_json(output / 'environment.json')
    validate_environment(env)
    if done['source_hashes'] != env['source_hashes'] or done['seeds'] != env['seeds']:
        raise ValueError('Completion source or seeds differ from environment')
    for name, digest in done['file_hashes'].items():
        if Path(name).name != name or sha(output / name) != digest:
            raise ValueError(f'Result hash mismatch: {name}')
    plan = [from_json(c) for c in env['plan']]
    if (len(plan) != 3 or {c.degree for c in plan} != {1,4,8}
            or len({c.samples for c in plan}) != 1 or len(set(env['seeds'])) != 3):
        raise ValueError('Expected three degrees at fixed M and three seeds')
    cases = []
    for config in plan:
        for seed in env['seeds']:
            directory = load_json(output / f'prepared_{seed}.json')['path']
            c = checked_case(output / f'{config.case_id}_seed_{seed}.json', config, seed, directory)
            for rnd in range(1, config.rounds+1):
                rows = [r for r in c['round_records'] if r['round'] == rnd]
                if len(rows) != 3 or len({r['head_digest_after_public'] for r in rows}) != 1 or any(r['traffic'] != rows[0]['traffic'] for r in rows):
                    raise ValueError('Paired head or communication mismatch')
            metric_series = [[{k:v for k,v in m.items() if k != 'method'} for m in c['metrics'] if m['method'] == n] for n in ('B','E','D')]
            if not metric_series[0] == metric_series[1] == metric_series[2]:
                raise ValueError('Paired quality mismatch')
            cases.append(c)
    check_shared_cases(cases)
    if done['case_count'] != 9 or done['method_runs'] != 27 or done['mismatches'] != 0:
        raise ValueError('Incomplete completion record')
    groups, rows = {}, []
    for config in sorted(plan, key=lambda c:c.degree):
        group = sorted([c for c in cases if c['case_id'] == config.case_id], key=lambda c:c['seed'])
        comparisons = {ref:{field:paired(group,ref,field) for field in ('generation_seconds','training_pipeline_seconds','with_shared_preparation_seconds')} for ref in ('B','E')}
        groups[config.case_id] = comparisons
        for c in group:
            for n in ('B','E','D'):
                s = c['summary'][n]
                r = dict(degree=config.degree, samples=config.samples, edges=c['edge_count'], seed=c['seed'], method=n)
                for field in ('training_pipeline_seconds','generation_seconds','private_seconds','public_seconds','exchange_seconds',
                              'teacher_recompute_fraction_after_bootstrap','candidate_size_after_bootstrap','certified_edge_fraction_after_bootstrap',
                              'student_forward_endpoints','public_optimizer_steps','persistent_method_array_bytes'):
                    r[field] = s[field]
                rr = [r for r in c['round_records'] if r['method'] == n]
                r['teacher_forward_endpoints_including_bootstrap'] = sum(r['teacher_forward_endpoints'] for r in rr)
                r['mean_positive_relation_fraction'] = st.mean(r['positive_relation_fraction'] for r in rr)
                r['B_generation_share_percent'] = 100*c['summary']['B']['generation_seconds']/c['summary']['B']['training_pipeline_seconds']
                r['traffic_bytes'] = s['traffic']['total_bytes']
                rows.append(r)
    target = output / 'graph_analysis'
    target.mkdir(exist_ok=True)
    (target / 'implementation.json').write_text(json.dumps({
        'scope': 'Version at diagnostic generation; core training/resume is frozen separately by environment.json',
        'graph_driver_sources': {p.name:sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'core_training_sources': env['source_hashes'],
        'completion_sha256': sha(output / 'completed.json'),
    },indent=2),encoding='utf-8')
    (target / 'diagnostics.json').write_text(json.dumps(groups, ensure_ascii=False, indent=2), encoding='utf-8')
    with (target / 'diagnostics.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    text = ['# 图密度实验诊断', '', '先同配置同seed计算比值/省时，再取三个配对值的中位数。负数代表D更慢；不跨degree合并。', '',
            '|degree|对照|生成耗时减少|头训练流程耗时减少|流程省时秒|流程胜出数|', '|---:|---|---:|---:|---:|---:|']
    if env.get('preset') != 'full':
        text.insert(2, '**缩小配置的路径验证，不能作为正式性能结论。**\n')
    for config in sorted(plan,key=lambda c:c.degree):
        for ref in ('B','E'):
            p = groups[config.case_id][ref]
            g,t = p['generation_seconds'],p['training_pipeline_seconds']
            text.append(f"|{config.degree}|D/{ref}|{g['percent_less']:.2f}%|{t['percent_less']:.2f}%|{t['seconds_saved']:.3f}|{t['wins']}/3|")
    text += ['', 'diagnostics.csv记录实际教师端点、重算比例、平均候选集大小、认证边比例、正关系比例、SGD步数、分阶段耗时和持久数组。独立峰值内存见上级memory_summary.csv；默认只有最大degree，不能假称所有degree均有进程峰值测量。', '',
             '固定M下，B每轮只对每个公共样本做一次教师前向，不随边数重复前向。图密度增加也增加公共SGD预算；它检验更密图的实际开销，不是固定学生预算实验。', '',
             'B/E/D在各配置内逐轮头摘要、通信和全部保存的评估一致；不要求不同degree之间轨迹一致。冻结编码器、串行CPU头训练、内存消息；不包含实网、选举或故障恢复。', '',
             '省时T不含评估/oracle/编码器准备；C0+T沿用共享最大公共池准备成本口径。degree=1来自历史运行，跨degree绝对时间可能受运行批次环境变化影响；每个degree内部的B/E/D配对仍为主要依据。']
    (target / 'report.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    return groups


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    analyze(parser.parse_args().output)
