"""Generate paired seed-level estimates and the generation share of B."""

from collections import defaultdict
from statistics import mean

from experiments.snapshot_certification_timing.design import require, sha
from ..report import eligible, write_csv
from .design import METHODS, PARTITIONS, cell_id


def metrics(run, dimensions, classes):
    stages = ('private_seconds', 'generation_seconds', 'exchange_seconds', 'public_seconds')
    result = {stage: sum(r[stage] for r in run['timing']) for stage in stages}
    head = run['setup_seconds'] + sum(r['seconds'] for r in run['timing'])
    require(head > 0 and result['generation_seconds'] > 0, 'Invalid timing total')
    return dict(head_seconds=head, **result,
                generation_share_pct=100*result['generation_seconds']/head,
                endpoints=sum(run['client_endpoints']),
                scoring_macs=classes*sum(x*w for x, w in zip(run['client_endpoints'], dimensions, strict=True)),
                **{key: run[key] for key in ('setup_seconds', 'load_seconds', 'preparation_seconds',
                                             'cache_bytes', 'protocol_bytes', 'input_peak_bytes',
                                             'process_peak_bytes', 'suspend_seconds')},
                **{key: run['traffic'][key] for key in ('up_bytes', 'down_bytes', 'total_bytes')},
                **{key: run['power'].get(key, 0) for key in ('ac', 'battery', 'unknown')})


def differences(groups, method):
    result = {}
    for field in ('generation_seconds', 'head_seconds'):
        ref = [p[method][field] for p in groups]
        d = [p['D'][field] for p in groups]
        saved = mean(ref)-mean(d) if ref else None
        result.update({f'{field}_saved': saved,
                       f'{field}_saved_pct': 100*saved/mean(ref) if ref else None,
                       f'{field}_wins': sum(x < y for x, y in zip(d, ref, strict=True))})
    return result


def report(out, manifest, groups, audits):
    full = manifest['preset'] == 'full'
    required = 3 if full else 1
    chosen, original, seen = defaultdict(list), defaultdict(list), set()
    runs, pairs, summaries, quality, client_rows = [], [], [], [], []
    for block, attempt, group in groups:
        cell, repeat = cell_id(block['case']), block['repeat']
        good = eligible(group, manifest['preset'])
        key = (cell, repeat)
        primary = good and key not in seen
        base = dict(cell=cell, repeat=repeat, attempt=attempt, order=block['order'], eligible=good, primary=primary)
        measured = {m: metrics(group[m], manifest['config']['dimensions'], manifest['config']['classes']) for m in METHODS}
        runs.extend(dict(**base, method=m, **value) for m, value in measured.items())
        pairs.extend(dict(**base, reference=m, **differences([measured], m)) for m in 'BE')
        if attempt == 0:
            original[cell].append(measured)
        if primary:
            seen.add(key)
            chosen[cell].append(measured)
    lines = ['# Fashion-MNIST 上的 B、同界 E 与当前 D', '',
             f'逐边核对 {sum(a["comparisons"] for a in audits.values()):,} 次，零差异。'
             f'通过轨迹核对的计时进程 {len(runs)} 个，含补测。', '',
             '| 配置 | 对照 | 有效块 | B 的生成占比 | 生成省时 | 完整头部省时 | 完整头部省秒 | 判定 |',
             '|---|---|---:|---:|---:|---:|---:|---|']

    def fmt(x, percent=False):
        return '—' if x is None else f'{x:.2f}%' if percent else f'{x:+.4f}'

    for case in manifest['cases']:
        cell = cell_id(case)
        require(len(original[cell]) == required and len(chosen[cell]) <= required, 'Incomplete or duplicate timing blocks')
        for label, group in (('original', original[cell]), ('primary', chosen[cell])):
            b_share = (100*mean(p['B']['generation_seconds'] for p in group) / mean(p['B']['head_seconds'] for p in group)
                       if group else None)
            for method in 'BE':
                delta = differences(group, method)
                verdict = '短测'
                if full:
                    verdict = '配对不足' if len(group) != required else '达标' if (
                        delta['head_seconds_saved_pct'] >= manifest['threshold_pct'] and
                        delta['head_seconds_wins'] >= manifest['minimum_wins']) else '未达标'
                summaries.append(dict(cell=cell, **case, scope=label, reference=method, blocks=len(group),
                                      b_generation_share_pct=b_share, verdict=verdict, **delta))
                if label == 'primary':
                    lines.append(f"| {cell} | D/{method} | {len(group)}/{required} | {fmt(b_share, True)} | "
                                 f"{fmt(delta['generation_seconds_saved_pct'], True)} | "
                                 f"{fmt(delta['head_seconds_saved_pct'], True)} | "
                                 f"{fmt(delta['head_seconds_saved'])} | {verdict} |")
        for q in audits[cell, 'B']['evaluations']:
            quality.extend(dict(cell=cell, round=q['round'], **client) for client in q['clients'])
        for method in METHODS:
            for client, (width, n) in enumerate(zip(manifest['config']['dimensions'],
                                                   audits[cell, method]['client_endpoints'], strict=True)):
                client_rows.append(dict(cell=cell, method=method, client=client, width=width, endpoints=n,
                                        scoring_macs=n*width*manifest['config']['classes']))
    if full:
        lines.extend(['', '## 跨种子确认', ''])
        for part in PARTITIONS:
            for method in 'BE':
                subset = [r for r in summaries if r['partition'] == part and r['scope'] == 'primary'
                          and r['reference'] == method]
                wins = sum(r['verdict'] == '达标' for r in subset)
                verdict = '证据不足' if any(r['verdict'] == '配对不足' for r in subset) else '达标' if wins >= 2 else '未达标'
                lines.append(f'- {part}，D/{method} 达标种子 {wins}/{len(subset)}，划分判定{verdict}。')
    else:
        lines.extend(['', '小规模真实数据短测用于核对流程。'])
    lines.extend(['', '完整头部计入初始化和训练各轮。缓存读取和共同准备单列。'
                  '逐轮轨迹中三种方法的学生目标、头参数和通信相同。'
                  '各评估点的共同 ACC、NMI、ARI 和簇占用见 quality.csv。'])
    files = {}
    for name, rows in [('runs', runs), ('paired_blocks', pairs), ('comparisons', summaries), ('quality', quality),
                       ('client_widths', client_rows)]:
        path = out/f'{name}.csv'
        write_csv(path, rows)
        files[path.name] = sha(path)
    path = out/'report.md'
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    files[path.name] = sha(path)
    return files
