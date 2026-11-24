"""Write reports from matched acceptable runs and preserve every attempt."""

from collections import defaultdict
from statistics import mean, median

from experiments.snapshot_certification_timing.design import sha
from ..fashion_confirmation.design import cell_id
from ..fashion_confirmation.report import metrics
from ..report import write_csv
from .gather import BASE
from .screening import ORDERS

HEAD_THRESHOLD = 3.
MIN_WINS = 5


def save(root, lines, tables):
    files = {}
    for filename, rows in tables:
        if rows:
            path = root/filename
            write_csv(path, rows)
            files[filename] = sha(path)
    path = root/'report.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    files[path.name] = sha(path)
    return files


def percent(value):
    return '—' if value is None else f'{value:+.2f}%'


def screening_report(root, screened, summaries, status, candidate):
    lines = [
        '# 特征收集方式筛选', '',
        f'筛选状态 **{status}**。进入下一阶段的候选为 **{candidate or "无"}**。', '',
        '| 配置 | 候选 | 有效配对块 | 收集加打分省时 | 达到 10% |',
        '| --- | --- | ---: | ---: | --- |',
    ]
    for row in summaries:
        lines.append(f'| {row["cell"]} | {row["candidate"]} | {row["eligible_blocks"]} | '
                     f'{percent(row["saved_pct"])} | {"是" if row["passed"] else "否"} |')
    lines.extend(['', '收集加打分包含偏置加法和赢家选择。复用缓冲区首次分配计入耗时。'
                  '另保留各特征宽度和刷新比例下的收集耗时与总耗时。'])
    runs, strata = [], []
    for cell, result in screened.items():
        for block in result['blocks']:
            for method, run in block['runs'].items():
                base = dict(cell=cell, repeat=block['repeat'], attempt=block['attempt'],
                            eligible=block['eligible'], order='/'.join(block['order']), method=method)
                runs.append(dict(**base, seconds=run['seconds'], setup_seconds=run['setup_seconds'],
                                 scratch_bytes=run['scratch_bytes'], suspend_seconds=run['suspend_seconds'],
                                 **run['power']))
                strata.extend(dict(**base, **row) for row in run['strata'])
    return save(root, lines, [('seeds.csv', summaries), ('replays.csv', runs), ('strata.csv', strata)])


def compare(blocks, reference):
    ref = [b[reference]['head_seconds'] for b in blocks]
    trial = [b['optimized']['head_seconds'] for b in blocks]
    differences = [a-b for a, b in zip(ref, trial, strict=True)]
    generation = [b[reference]['generation_seconds']-b['optimized']['generation_seconds'] for b in blocks]
    return dict(
        head_saved_seconds=mean(differences) if ref else None,
        head_saved_pct=100*mean(differences)/mean(ref) if ref else None,
        head_median_saved_seconds=median(differences) if ref else None,
        generation_saved_seconds=mean(generation) if ref else None,
        head_wins=sum(delta > 0. for delta in differences),
    )


def confirmation_report(root, manifest, timing):
    cfg = manifest['config']
    full = manifest['preset'] == 'full'
    required = len(ORDERS) if full else 1
    runs, pairs, accepted = [], [], defaultdict(list)
    for block, group in timing:
        base = {**block, 'order': '/'.join(block['order'])}
        values = {name: metrics(run, cfg['dimensions'], cfg['classes']) for name, run in group.items()}
        pairs.extend(dict(**base, reference=ref, **compare([values], ref)) for ref in (BASE, 'B'))
        runs.extend(dict(**base, method=name, scratch_bytes=group[name]['scratch_bytes'], **value)
                    for name, value in values.items())
        if block['eligible']:
            accepted[block['cell']].append(values)
    summary = []
    for case in manifest['cases']:
        cell = cell_id(case)
        blocks = accepted[cell]
        ready = len(blocks) == required
        for ref in (BASE, 'B'):
            result = compare(blocks, ref)
            passes = (result['head_saved_pct'] >= HEAD_THRESHOLD and result['head_wins'] >= MIN_WINS
                      if ready and full else None)
            summary.append(dict(cell=cell, **case, reference=ref, eligible_blocks=len(blocks),
                                passed=passes, **result))
    if any(row['eligible_blocks'] != required for row in summary):
        status = 'confirmation_incomplete'
    elif not full:
        status = 'smoke_complete'
    else:
        strong = [r for r in summary if r['reference'] == BASE and r['partition'] == 'dirichlet_0.1']
        iid = [r for r in summary if r['reference'] == BASE and r['partition'] == 'iid']
        passed = sum(row['passed'] for row in strong) >= 2 and all(r['head_saved_pct'] > -HEAD_THRESHOLD for r in iid)
        status = 'confirmed' if passed else 'confirmation_failed'
    lines = [
        '# D 特征收集优化的新种子确认', '',
        f'冻结候选 **{manifest["candidate"]}**。判定 **{status}**。',
        '主判定比较改进 D 与旧 D。相对 B 的结果单独列出。',
        '缓冲区首次分配计入生成阶段和完整头部。正值表示改进 D 更快。', '',
        '| 配置 | 对照 | 有效配对块 | 完整头部省时 | 配对胜场 | 生成省时（秒） |',
        '| --- | --- | ---: | ---: | ---: | ---: |',
    ]
    for row in summary:
        generation = row['generation_saved_seconds']
        lines.append(f'| {row["cell"]} | {row["reference"]} | {row["eligible_blocks"]}/{required} | '
                     f'{percent(row["head_saved_pct"])} | {row["head_wins"]} | '
                     f'{generation:+.4f} |' if generation is not None else
                     f'| {row["cell"]} | {row["reference"]} | 0/{required} | — | — | — |')
    if full and status != 'confirmation_incomplete':
        for part in ('iid', 'dirichlet_0.1'):
            vs_b = [row for row in summary if row['partition'] == part and row['reference'] == 'B']
            lines.extend(['', f'{part} 上相对 B 达到 3% 且至少赢 5/6 块的种子数为 '
                              f'{sum(row["passed"] for row in vs_b)}/{len(vs_b)}。'])
    return save(root, lines, [('seeds.csv', summary), ('paired_blocks.csv', pairs), ('runs.csv', runs)]), status
