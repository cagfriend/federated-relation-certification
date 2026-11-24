"""Pair plain timings and report independent diagnostic phase measurements."""

from collections import defaultdict
from statistics import mean

from experiments.snapshot_certification_timing.design import sha
from ..fashion_confirmation.design import cell_id
from ..fashion_confirmation.report import metrics
from ..report import write_csv
from .phases import PHASES


def diagnostic(pair):
    phases = {method: {phase: sum(row[phase] for row in run['profile_rows']) for phase in PHASES}
              for method, run in pair.items()}
    total = {method: sum(row['generation_seconds'] for row in run['timing']) for method, run in pair.items()}
    score_saved = phases['B']['scoring'] - phases['D']['scoring']
    bootstrap_extra = phases['D']['bootstrap'] - phases['B']['bootstrap']
    extra_by_phase = {key: phases['D'][key]-phases['B'][key]
                      for key in PHASES if key not in ('scoring', 'bootstrap')}
    remainder = {method: total[method]-sum(phases[method].values()) for method in pair}
    major = max(extra_by_phase, key=extra_by_phase.get)
    return dict(scoring_saved=score_saved, bootstrap_extra=bootstrap_extra,
                other_phases_extra=sum(extra_by_phase.values()), largest_phase=major,
                largest_phase_extra=extra_by_phase[major],
                remainder_extra=remainder['D']-remainder['B'],
                generation_extra=total['D']-total['B'])


def report(out, manifest, blocks):
    cfg = manifest['config']
    timing, profiles, accepted = [], [], defaultdict(list)
    profile_by_cell = {}
    for block, pair in blocks:
        base = {k: v for k, v in block.items() if k not in ('hashes', 'order')}
        if block['stage'] == 'timing':
            b, d = (metrics(pair[m], cfg['dimensions'], cfg['classes']) for m in ('B', 'D'))
            row = dict(**base, order='/'.join(block['order']),
                       b_endpoints=b['endpoints'], d_endpoints=d['endpoints'],
                       b_macs=b['scoring_macs'], d_macs=d['scoring_macs'],
                       b_head_seconds=b['head_seconds'], d_head_seconds=d['head_seconds'],
                       b_generation_seconds=b['generation_seconds'], d_generation_seconds=d['generation_seconds'],
                       head_saved=b['head_seconds']-d['head_seconds'],
                       generation_saved=b['generation_seconds']-d['generation_seconds'])
            timing.append(row)
            if block['eligible']:
                accepted[block['cell']].append(row)
        else:
            for method, run in pair.items():
                profiles.extend(dict(**base, method=method, **row) for row in run['profile_rows'])
            if block['eligible']:
                profile_by_cell[block['cell']] = diagnostic(pair)

    diagnostics = []
    lines = [
        '# Fashion-MNIST 教师关系生成耗时归因', '',
        '无插桩计时沿用 E55 完整头部窗口。阶段数据来自单独的插桩配对。',
        '下表中正的省时表示 D 更快，正的额外耗时表示 D 更慢，单位均为秒。', '',
        '| 配置 | 无插桩有效块 | D 完整头部省时 | D 生成省时 | 插桩打分省时 | '
        '首轮额外耗时 | 其余阶段额外耗时 | 最大增量阶段 | 未归入阶段的差 | 诊断判据 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |',
    ]
    complete = True
    for case in manifest['cases']:
        cell = cell_id(case)
        rows = accepted[cell]
        n = len(rows)
        paired = f'{n}/{manifest["repeats"]}'
        ready = n == manifest['repeats']
        complete &= ready and cell in profile_by_cell
        timings = [f'{mean(row[key] for row in rows):+.4f}' if ready else '—'
                   for key in ('head_saved', 'generation_saved')]
        phases = profile_by_cell.get(cell)
        details = ['—']*6
        if phases:
            plain_extra = -mean(row['generation_saved'] for row in rows) if ready else None
            aligned = plain_extra is not None and plain_extra*phases['generation_extra'] > 0.
            actionable = aligned and phases['largest_phase_extra'] > abs(phases['remainder_extra'])
            diagnostics.append(dict(cell=cell, plain_generation_extra=plain_extra,
                                    direction_agrees=aligned, actionable=actionable, **phases))
            details = [f'{phases[key]:+.4f}' for key in ('scoring_saved', 'bootstrap_extra', 'other_phases_extra')]
            details.extend([f'{phases["largest_phase"]} ({phases["largest_phase_extra"]:+.4f})',
                            f'{phases["remainder_extra"]:+.4f}',
                            '可定位' if actionable else '需复核'])
        lines.append('| ' + ' | '.join([cell, paired, *timings, *details]) + ' |')
    lines.extend(['', '打分省时只对比第 2 轮起的矩阵乘法和偏置加法。',
                  '首轮合计包含全量打分和方法初始化。其余阶段合计包含端点和候选处理。'
                  '未归入阶段的差包括计时器自身开销，因此阶段差只用于诊断。'])
    if manifest['preset'] == 'smoke':
        lines.extend(['', '小规模短测仅用于检查流程。'])
    files = {}
    for name, rows in [('paired_blocks.csv', timing), ('phases.csv', profiles),
                       ('diagnostics.csv', diagnostics)]:
        if not rows:
            continue
        path = out/name
        write_csv(path, rows)
        files[name] = sha(path)
    path = out/'report.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    return {**files, path.name: sha(path)}, complete
