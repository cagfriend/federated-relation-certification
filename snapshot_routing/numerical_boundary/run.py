"""Audit E48's remaining wrong edges and test targeted numerical guards."""

import argparse
import csv
import os
from pathlib import Path

for variable in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'LOKY_MAX_CPU_COUNT'):
    os.environ[variable] = '1'

import torch
from threadpoolctl import threadpool_limits

from experiments.snapshot_certification_timing.design import ROOT, environment, require, seal, sha, write
from ..bias_numerical.design import comparison_fixtures, mixed_cancellation, weight_prefix
from ..numerical_check.design import near_tie
from ..numerical_check.run import metadata
from ..report import write_csv
from .audit import REPAIRS, audit
from .replay import references, screen

PACKAGE = Path(__file__).resolve().parent
E48 = ROOT/'docs/evidence/e48_bias_numerical/cases.csv'
CANCELLATION = ('cancellation_p53_d17_middle', 'heldout_mixed_cancellation_p54_d17_middle',
                'heldout_mixed_cancellation_p56_d33_after')
PREFIX = ('heldout_weight_prefix_p55_n48', 'heldout_weight_prefix_p58_n192')
FOCUS = (*CANCELLATION, *PREFIX)


def fixtures(preset):
    original = comparison_fixtures('full')
    require(len(original) == 21 and set(FOCUS).issubset({case.name for case in original}), 'E48 matrix changed')
    if preset == 'smoke':
        return [case for case in original if case.name in (*FOCUS, 'near_tie_k10')]
    return [*original, weight_prefix(56, 37), mixed_cancellation(55, 19, (0, 1, 2)),
            mixed_cancellation(57, 41, (0, 2, 1)), near_tie(33)]


def summarize(case, rows, events):
    counts = ('edges', 'b_vs_rational', 'old_wrong', 'current_wrong', 'current_introduced_vs_old', 'current_forward')
    summary = dict(**metadata(case), **{f'{key}_total': sum(row[key] for row in rows) for key in counts})
    for repair in REPAIRS:
        for key in ('wrong', 'fixed', 'remaining', 'introduced', 'forward'):
            summary[f'{repair}_{key}'] = sum(row[f'{repair}_{key}'] for row in rows)
        for reason in ('scale', 'rebuild'):
            summary[f'{repair}_{reason}_rounds'] = sum(row[f'{repair}_fallback'] == reason for row in rows)
    for key in ('b_winner_excluded', 'local_refresh_disagrees', 'rescue_candidate_matches',
                'b_slice_refresh_matches', 'both_probes_match', 'exact_prefix_matches'):
        summary[key] = sum(event[key] is True for event in events)
    return summary


def expected_e48():
    with E48.open(encoding='utf-8-sig', newline='') as file:
        return {row['name']: row for row in csv.DictReader(file)}


def verify_original(expected, row):
    same = row['fixture_sha256'] == expected['fixture_sha256']
    mapping = dict(old_wrong_total='old_edges_vs_b', current_wrong_total='new_edges_vs_b',
                   current_introduced_vs_old_total='introduced', b_vs_rational_total='b_vs_exact_edges',
                   edges_total='paired_edge_positions')
    return same and all(row[key] == int(expected[value]) for key, value in mapping.items())


def report(out, rows, wrong, summary, failures, preset, replay_pairs):
    write_csv(out/'cases.csv', summary)
    write_csv(out/'rounds.csv', rows)
    if wrong:
        write_csv(out/'edges.csv', wrong)
    verdict = '短测' if preset == 'smoke' else '通过' if not any(failures.values()) else '未通过'
    lines = ['# 数值边界定位和试验性修补', '', f'判定：**{verdict}**。{len(summary)} 个实例，'
             f'{sum(row["edges_total"] for row in summary):,} 个轮次—边位置。', '',
             '| 实例 | 当前 D 对 B | 仅权重修补 | 仅稠密回退 | 合并残留 | 合并新增 | B 对有理数 |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for row in summary:
        lines.append(f"| {row['name']} | {row['current_wrong_total']} | {row['weight_wrong']} | "
                     f"{row['dense_wrong']} | {row['combined_remaining']} | {row['combined_introduced']} | "
                     f"{row['b_vs_rational_total']} |")
    lines.extend(['', '## 机制探针', '',
                  '| 实例 | 当前错边 | 端点排除 B 赢家 | 局部刷新与 B 不同 | 补候选即匹配 | B 切片刷新即匹配 | 精确前缀即匹配 |',
                  '|---|---:|---:|---:|---:|---:|---:|'])
    for row in summary:
        if row['name'] not in FOCUS:
            continue
        prefix = row['exact_prefix_matches'] if row['name'] in PREFIX else '—'
        lines.append(f"| {row['name']} | {row['current_wrong_total']} | {row['b_winner_excluded']} | "
                     f"{row['local_refresh_disagrees']} | {row['rescue_candidate_matches']} | "
                     f"{row['b_slice_refresh_matches']} | {prefix} |")
    lines.extend(['', '同一错边可涉及多个机制。探针复用原缓存，只干预当前轮；独立修补轨迹见 cases.csv。'
                  '基准 B 是同环境的全批 float64；有理数对照用于识别 B 自身的舍入差异。', '', '## 门槛检查', ''])
    lines.extend(f"- {key}：{', '.join(names) if names else '通过'}" for key, names in failures.items())
    if replay_pairs:
        lines.extend(['', '## 真实教师轨迹资源筛查', '',
                      '| 配置 | 已配对 | 合并生成耗时变化 | 全批触发（每次回放） | 合并额外持久缓存 B |',
                      '|---|---:|---:|---:|---:|'])
        for cell in dict.fromkeys(row['cell'] for row in replay_pairs):
            pairs = [row for row in replay_pairs if row['cell'] == cell]
            ratio = sum(p['combined_seconds'] for p in pairs)/sum(p['current_seconds'] for p in pairs)
            p = pairs[0]
            triggers = p['combined_scale_client_rounds'] + p['combined_rebuild_client_rounds']
            lines.append(f"| {cell} | {len(pairs)} | {100*(ratio-1):+.2f}% | {triggers} | "
                         f"{p['combined_cache_bytes']-p['current_cache_bytes']:+,} |")
        lines.extend(['', '同进程配对回放，供筛查额外生成开销。完整训练时间与跨环境表现另需确认。'])
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')


def execute(out, preset, source, replay):
    require(not out.exists() or not any(out.iterdir()), 'Use an empty output directory')
    cases = fixtures(preset)
    expected = expected_e48()
    require(len(cases) == len({case.name for case in cases}) == (6 if preset == 'smoke' else 25),
            'Unexpected fixture count')
    archived = references(source) if replay else []
    touched = [*PACKAGE.glob('*.py'), E48, PACKAGE/'README.md',
               *(PACKAGE.parent/name for name in ('bias_numerical/design.py', 'bias_numerical/audit.py',
                                                  'numerical_check/design.py', 'numerical_check/audit.py',
                                                  'bias_resources/worker.py')),
               *(ROOT/f'experiments/public_scaling/{file}.py' for file in ('certification','endpoint_bias'))]
    marker = out/'manifest.json'
    write(marker, dict(preset=preset, environment=environment(), fixtures=[metadata(case) for case in cases],
                       traces={cell: ref['payload_sha256'] for cell, _, ref in archived},
                       sources={p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(touched)}))
    rows, events, summary = [], [], []
    for case in cases:
        print(f'Audit {case.name}: {len(case.weights)} snapshots', flush=True)
        observed, details = audit(case)
        require(len(observed) == len(case.weights), f'Incomplete snapshots: {case.name}')
        rows.extend(observed)
        events.extend(details)
        summary.append(summarize(case, observed, details))
    failures = dict(
        e48_not_reproduced=[row['name'] for row in summary if row['name'] in expected
                            and not verify_original(expected[row['name']], row)],
        weight_witness_remaining=[row['name'] for row in summary if row['name'] in PREFIX and row['weight_wrong']],
        cancellation_witness_remaining=[row['name'] for row in summary if row['name'] in CANCELLATION and row['dense_wrong']],
        combined_differs_from_b=[row['name'] for row in summary if row['combined_wrong']],
        replay_differs_from_b=[],
    )
    pairs = []
    if archived and not any(failures.values()):
        pairs, replay_rounds = screen(archived)
        write_csv(out/'replay_pairs.csv', pairs)
        write_csv(out/'replay_rounds.csv', replay_rounds)
        failures['replay_differs_from_b'] = sorted({row['cell'] for row in pairs
                                                   if row['combined_mismatches'] or row['current_mismatches']})
    report(out, rows, events, summary, failures, preset, pairs)
    passed = (not any(failures.values())) if preset == 'full' else None
    paths = sorted(p for p in out.iterdir() if p.is_file())
    seal(out/'completed.json', dict(manifest=sha(marker), preset=preset, passed=passed, failures=failures,
                                    replay_requested=replay, replay_completed=bool(pairs),
                                    files={p.name: sha(p) for p in paths}))
    print(f'Finished: {out/"report.md"}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('full', 'smoke'), default='full')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--replay', action='store_true', help='Screen resource cost after synthetic checks pass')
    parser.add_argument('--source', type=Path, default=ROOT/'outputs/snapshot_routing_confirmation_full')
    args = parser.parse_args()
    require(not args.replay or args.preset == 'full', 'Replay requires the full numerical matrix')
    out = (args.output or ROOT/'outputs'/f'snapshot_routing_numerical_boundary_{args.preset}').resolve()
    source = args.source.resolve()
    require(not args.replay or not (out.is_relative_to(source) or source.is_relative_to(out)),
            'Output overlaps E42 source directory')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        execute(out, args.preset, source, args.replay)


if __name__ == '__main__':
    main()
