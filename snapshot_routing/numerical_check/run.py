"""Run and archive deterministic floating-point boundary fixtures."""

import argparse
import hashlib
import os
from pathlib import Path

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import numpy as np
import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import ROOT, environment, read, receipt, require, seal, sealed, sha, write

from ..report import write_csv
from .audit import MODES, audit
from .design import fixtures

PACKAGE = Path(__file__).resolve().parent
OBSERVATIONS = ('edges_vs_b', 'b_label_excluded', 'exact_label_excluded', 'refresh_vs_b')


def metadata(case):
    checksum = hashlib.sha256()
    for array in (case.features, case.edges, case.weights, case.biases):
        checksum.update(np.ascontiguousarray(array).tobytes())
    return dict(name=case.name, family=case.family, rounds=len(case.weights), samples=len(case.features),
                edges=len(case.edges), feature_width=case.features.shape[1], classes=case.weights.shape[1],
                fixture_sha256=checksum.hexdigest())


def snapshot_archive(path, case):
    path.parent.mkdir(exist_ok=True)
    temp = path.with_suffix('.part')
    with temp.open('wb') as handle:
        np.savez(handle, features=case.features, edges=case.edges, weights=case.weights, biases=case.biases)
    temp.replace(path)
    return sha(path)


def report(out, results):
    summary, details = [], []
    for case in results:
        spec, rounds = case['case'], case['rounds']
        row = dict(spec, b_vs_exact_labels=sum(r['b_vs_exact_labels'] for r in rounds),
                   b_vs_exact_edges=sum(r['b_vs_exact_edges'] for r in rounds))
        for method in MODES:
            checked = sum(r[f'{method}_edges_vs_b'] is not None for r in rounds)
            row[f'{method}_compared_rounds'] = checked
            row[f'{method}_compared_edges'] = checked*spec['edges']
            row[f'{method}_exceptions'] = sum(r[f'{method}_exception'] for r in rounds)
            row.update({f'{method}_{k}': sum(r[f'{method}_{k}'] or 0 for r in rounds) for k in OBSERVATIONS})
        row['status'] = ('different' if any(row[f'{m}_edges_vs_b'] for m in MODES)
                         else 'incomplete' if any(row[f'{m}_exceptions'] for m in MODES) else 'matches_B')
        summary.append(row)
        details.extend(dict(case=spec['name'], family=spec['family'], **r) for r in rounds)
    write_csv(out/'cases.csv', summary)
    write_csv(out/'rounds.csv', details)
    failures = sum(r['status'] != 'matches_B' for r in summary)
    lines = ['# 关系认证浮点边界核验', '',
             f'完成 {len(summary)} 个固定合成实例，其中 {failures} 个未满足完整 E/D 对 B 零关系差异。'
             f'E/D 对 B 共核对 {sum(r[f"{m}_compared_edges"] for r in summary for m in MODES):,} 条边。', '',
             '| 实例 | 轮次 | B 对有理数边差异 | E 对 B 边差异 | D 对 B 边差异 | 生成异常 |',
             '|---|---:|---:|---:|---:|---:|']
    for r in summary:
        lines.append(f"| {r['name']} | {r['rounds']} | {r['b_vs_exact_edges']} | {r['E_edges_vs_b']} | "
                     f"{r['D_edges_vs_b']} | {r['E_exceptions']+r['D_exceptions']} |")
    lines += ['', 'B 为原全量 float64 实现。有理数参考对传入的 binary64 特征和权重做精确乘加。'
               '两类差异按独立参照统计。', '',
               'cases.csv 另列候选排除与回退标签分歧的次数。各例 JSON 记录每类首见差异和中间状态。'
               'witnesses 目录保存出现任一差异的完整原始输入序列。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def execute(out, preset, case_name, resume):
    cases = [c for c in fixtures(preset) if case_name is None or c.name == case_name]
    require(cases, f'Unknown fixture {case_name}')
    require(len({c.name for c in cases}) == len(cases), 'Fixture names must be unique')
    tracked = [*sorted(PACKAGE.glob('*.py')), PACKAGE/'README.md', PACKAGE.parent/'report.py',
               ROOT/'experiments/public_scaling/certification.py']
    manifest = dict(preset=preset, fixtures=[metadata(c) for c in cases], environment=environment(),
                    sources={p.relative_to(ROOT).as_posix(): sha(p) for p in tracked})
    marker = out/'manifest.json'
    if marker.exists():
        require(resume and read(marker) == manifest, 'Resume requires the same fixtures, code and runtime')
    else:
        require(not out.exists() or not any(out.iterdir()), 'Use an empty output directory')
        write(marker, manifest)
    identity = sha(marker)
    completed = out/'completed.json'
    old = sealed(completed) if receipt(completed).exists() else None
    records, hashes = [], {}
    for case in cases:
        path = out/'cases'/f'{case.name}.json'
        witness = out/'witnesses'/f'{case.name}.npz'
        if not receipt(path).exists():
            require(old is None, 'Completed run lost an experiment record')
            print(f'{case.name}: {len(case.weights)} snapshots', flush=True)
            rows, events = audit(case)
            hash_ = snapshot_archive(witness, case) if events else None
            seal(path, dict(manifest=identity, case=metadata(case), rounds=rows, first_events=events,
                            witness_sha256=hash_))
        stored = sealed(path)
        require(stored['manifest'] == identity and stored['case'] == metadata(case) and
                [r['round'] for r in stored['rounds']] == list(range(1,len(case.weights)+1)),
                'Fixture result changed')
        if stored['witness_sha256'] is not None:
            require(sha(witness) == stored['witness_sha256'], 'Witness input changed')
        records.append(stored)
        hashes[path.relative_to(out).as_posix()] = sha(path)
    done = dict(manifest=identity, records=hashes)
    require(old is None or old == done, 'Completion record changed')
    report(out, records)
    seal(completed, done)
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full','smoke'), default='full')
    parser.add_argument('--case', help='Recompute one named fixture')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    opts = parser.parse_args()
    require(opts.case is None or any(c.name == opts.case for c in fixtures(opts.preset)), 'Unknown fixture')
    name = f'snapshot_routing_numerical_{opts.preset}' + (f'_{opts.case}' if opts.case else '')
    out = (opts.output or ROOT/'outputs'/name).resolve()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(out, opts.preset, opts.case, opts.resume)


if __name__ == '__main__':
    main()
