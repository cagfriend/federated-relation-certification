"""Confirmation reports: seed is the statistical unit, repeats average out.

Aggregation and decision rules are frozen in PREREGISTRATION.md:
per (partition, tier), each seed's method time is the mean of its two
repeats; paired ratios are computed per seed and summarized by median
and range over the three seeds. The candidate-tier decision (C1/C2/C3)
is evaluated mechanically here.
"""
import csv, json, statistics as st
from pathlib import Path
from .design import METHODS, DECISION, PRIMARY_PRIVATE_LIMIT, QUALITY_ACC_DROP

PHASES = ('generation_seconds', 'head_pipeline_seconds', 'with_shared_preparation_seconds')


def _write_csv(path, rows):
    if not rows:
        return
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def _tier_limit(case_id):
    tail = case_id.rsplit('_priv', 1)[1]
    return None if tail == 'full' else int(tail)


def aggregate(runs):
    """runs: single-run records. Returns (run_rows, seed_rows, paired, noise, guardrails)."""
    run_rows = []
    for r in runs:
        s = r['summary'][r['method']]
        run_rows.append(dict(partition=r['partition'], seed=r['seed'], case_id=r['case_id'],
            private_limit=_tier_limit(r['case_id']), method=r['method'], repeat=r['repeat'],
            triple=r['triple'], position=r['position'],
            process_wall_seconds=r['process_wall_seconds'],
            process_peak_bytes=r['process_peak_bytes'],
            **{p: s[p] for p in PHASES},
            private_seconds=s['private_seconds'], public_seconds=s['public_seconds'],
            generation_fraction=s['generation_fraction'],
            persistent_method_array_bytes=s['persistent_method_array_bytes']))
    # Seed-level times: mean over repeats.
    groups = {}
    for row in run_rows:
        key = (row['partition'], row['seed'], row['case_id'], row['method'])
        groups.setdefault(key, []).append(row)
    seed_rows = []; noise = []
    for (part, seed, cid, method), group in sorted(groups.items()):
        base = dict(partition=part, seed=seed, case_id=cid,
                    private_limit=_tier_limit(cid), method=method, repeats=len(group))
        for p in PHASES + ('private_seconds', 'public_seconds'):
            base[p] = st.fmean(g[p] for g in group)
        seed_rows.append(base)
        for p in ('head_pipeline_seconds', 'generation_seconds'):
            vals = [g[p] for g in group]
            if len(vals) == 2 and st.fmean(vals) > 0:
                noise.append(dict(partition=part, seed=seed, case_id=cid, method=method,
                                  metric=p, repeat_relative_difference=abs(vals[0] - vals[1]) / st.fmean(vals)))
    # Paired per-seed ratios at seed level.
    paired = []
    by_key = {(r['partition'], r['seed'], r['case_id'], r['method']): r for r in seed_rows}
    case_ids = sorted({r['case_id'] for r in seed_rows})
    parts = sorted({r['partition'] for r in seed_rows})
    seeds = sorted({r['seed'] for r in seed_rows})
    for part in parts:
        for cid in case_ids:
            for ref in ('B', 'E'):
                for seed in seeds:
                    d = by_key.get((part, seed, cid, 'D')); o = by_key.get((part, seed, cid, ref))
                    if d and o:
                        paired.append(dict(partition=part, seed=seed, case_id=cid,
                            private_limit=_tier_limit(cid), comparison=f'D_over_{ref}',
                            **{p + '_ratio': d[p] / o[p] for p in PHASES},
                            **{p + '_saved_seconds': o[p] - d[p] for p in PHASES}))
    # Quality guardrail: candidate tier vs full tier, trajectory-level.
    guardrails = []
    finals = {}
    for r in runs:
        fm = r['summary'][r['method']]['final_metrics']
        finals[(r['partition'], r['seed'], r['case_id'])] = fm['mean']['acc'] if fm else None
    full_case = next((c for c in case_ids if _tier_limit(c) is None), None)
    cand_case = next((c for c in case_ids if _tier_limit(c) is not None), None)
    if full_case and cand_case:
        for part in parts:
            for seed in seeds:
                a = finals.get((part, seed, cand_case)); b = finals.get((part, seed, full_case))
                if a is not None and b is not None:
                    guardrails.append(dict(partition=part, seed=seed, case_id=cand_case,
                        reduced_final_mean_acc=a, full_final_mean_acc=b,
                        acc_change=a - b, within_guardrail=(a - b) >= -QUALITY_ACC_DROP - 1e-12))
    return run_rows, seed_rows, paired, noise, guardrails


def paired_summary(paired):
    out = []
    for part in sorted({r['partition'] for r in paired}):
        for cid in sorted({r['case_id'] for r in paired}):
            for comp in ('D_over_B', 'D_over_E'):
                rows = [r for r in paired if r['partition'] == part and r['case_id'] == cid and r['comparison'] == comp]
                if not rows:
                    continue
                entry = dict(partition=part, case_id=cid, private_limit=_tier_limit(cid), comparison=comp,
                             paired_seeds=len(rows),
                             head_wins=sum(r['head_pipeline_seconds_ratio'] < 1 for r in rows))
                for p in PHASES:
                    vals = [r[p + '_ratio'] for r in rows]
                    entry[p + '_median_ratio'] = st.median(vals)
                    entry[p + '_min_ratio'] = min(vals); entry[p + '_max_ratio'] = max(vals)
                    entry[p + '_median_saved_seconds'] = st.median([r[p + '_saved_seconds'] for r in rows])
                out.append(entry)
    return out


def decide(summary_rows, primary_limit=PRIMARY_PRIVATE_LIMIT):
    """Mechanical C1/C2/C3 evaluation for the candidate tier, per partition."""
    verdicts = []
    cand = [r for r in summary_rows if r['private_limit'] == primary_limit]
    for part in sorted({r['partition'] for r in cand}):
        db = next(r for r in cand if r['partition'] == part and r['comparison'] == 'D_over_B')
        de = next(r for r in cand if r['partition'] == part and r['comparison'] == 'D_over_E')
        c1 = db['head_pipeline_seconds_median_ratio'] <= DECISION['db_head_ratio_median_max']
        c2 = de['head_pipeline_seconds_median_ratio'] < DECISION['de_head_ratio_median_max']
        c3 = (db['head_wins'] >= DECISION['min_seed_wins'] and de['head_wins'] >= DECISION['min_seed_wins'])
        verdicts.append(dict(partition=part, C1_db_median_ratio=db['head_pipeline_seconds_median_ratio'],
            C1_pass=c1, C2_de_median_ratio=de['head_pipeline_seconds_median_ratio'], C2_pass=c2,
            db_head_wins=db['head_wins'], de_head_wins=de['head_wins'], C3_pass=c3,
            confirmed=c1 and c2 and c3))
    return verdicts


def reports(output, runs, blocks, expected_seeds=3):
    output = Path(output)
    run_rows, seed_rows, paired, noise, guardrails = aggregate(runs)
    summary_rows = paired_summary(paired)
    # Decide only when the preregistered candidate tier exists and every
    # seed has completed; smoke tiers use scaled limits, never a verdict.
    cand_rows = [r for r in summary_rows if r['private_limit'] == PRIMARY_PRIVATE_LIMIT]
    has_candidate = bool(cand_rows) and all(r['paired_seeds'] == expected_seeds for r in cand_rows)
    verdicts = decide(summary_rows) if has_candidate else []
    _write_csv(output / 'runs.csv', run_rows)
    _write_csv(output / 'seed_summary.csv', seed_rows)
    _write_csv(output / 'paired_cost.csv', paired)
    _write_csv(output / 'paired_summary.csv', summary_rows)
    _write_csv(output / 'timing_noise.csv', noise)
    _write_csv(output / 'quality_guardrails.csv', guardrails)
    (output / 'summary.json').write_text(json.dumps(dict(
        paired_summary=summary_rows, decision=verdicts,
        timing_noise_median={p: (st.median([n['repeat_relative_difference'] for n in noise if n['metric'] == p]) if any(n['metric'] == p for n in noise) else None)
                             for p in ('head_pipeline_seconds', 'generation_seconds')},
        blocks_verified=blocks), indent=2), encoding='utf-8')
    lines = ['# 独立性能确认报告', '',
             '新 seed、单方法独立进程、每运行 2 次技术重复；统计单位为 seed（重复先平均）。',
             '判定规则见 `PREREGISTRATION.md`，只针对候选档（私有上限 2048；smoke 档位不产生正式判定）。', '']
    if verdicts:
        lines += ['## 预注册判定（候选档）', '',
                  '| partition | C1 D/B 中位比值 ≤0.90 | C2 D/E 中位比值 <1.00 | C3 胜出（D/B, D/E） | 判定 |',
                  '|:--|:--|:--|:--|:--|']
        for v in verdicts:
            lines.append(f"| {v['partition']} | {v['C1_db_median_ratio']:.4f}（{'通过' if v['C1_pass'] else '未通过'}） | "
                         f"{v['C2_de_median_ratio']:.4f}（{'通过' if v['C2_pass'] else '未通过'}） | "
                         f"{v['db_head_wins']}/3, {v['de_head_wins']}/3（{'通过' if v['C3_pass'] else '未通过'}） | "
                         f"{'确认' if v['confirmed'] else '未确认'} |")
        ok = sum(v['confirmed'] for v in verdicts)
        overall = '两划分均确认' if ok == len(verdicts) else ('部分确认（见上表）' if ok else '未确认')
        lines += ['', f'**总判定：{overall}。**', '']
    lines += ['## 配对成本（seed 层中位）', '',
              '| partition | case_id | 对照 | seeds | D 头胜出 | generation 中位比值 | 头中位比值 | 头比值范围 | 头中位省秒 | 含准备中位比值 |',
              '|:--|:--|:--|--:|--:|--:|--:|:--|--:|--:|']
    for r in summary_rows:
        lines.append(f"| {r['partition']} | {r['case_id']} | {r['comparison']} | {r['paired_seeds']} | {r['head_wins']} | "
                     f"{r['generation_seconds_median_ratio']:.4f} | {r['head_pipeline_seconds_median_ratio']:.4f} | "
                     f"{r['head_pipeline_seconds_min_ratio']:.4f}–{r['head_pipeline_seconds_max_ratio']:.4f} | "
                     f"{r['head_pipeline_seconds_median_saved_seconds']:.4f} | {r['with_shared_preparation_seconds_median_ratio']:.4f} |")
    if noise:
        head_noise = [n['repeat_relative_difference'] for n in noise if n['metric'] == 'head_pipeline_seconds']
        lines += ['', '## 计时噪声（同 seed 两次重复相对差）', '',
                  f'完整头：中位 {st.median(head_noise):.4%}，最大 {max(head_noise):.4%}（{len(head_noise)} 对）。'
                  'seed 间差异与重复噪声分开报告；3 个 seed 的比值只报范围，不称置信区间。']
    if guardrails:
        lines += ['', '## 质量护栏（候选档相对完整档，轨迹级）', '',
                  '| partition | seed | ACC 变化 | 护栏（≥ −1 个百分点） |', '|:--|--:|--:|:--|']
        for g in guardrails:
            lines.append(f"| {g['partition']} | {g['seed']} | {g['acc_change']:+.4f} | {'通过' if g['within_guardrail'] else '越界'} |")
    lines += ['', '## 轨迹一致性', '',
              f"已核对组（划分 × seed × 档位）：{blocks.get('blocks_checked', 0)} 组；"
              f"组内 6 次运行非计时字段逐轮一致、重复间方法专属计数一致，mismatches={blocks.get('mismatches', 0)}。",
              '', '## 边界', '',
              '独立进程串行 CPU 计时，不是并行系统轮时延；进程墙钟与峰值内存只在 `runs.csv` 中描述性记录。'
              '休眠/暂停剔除只按 `PREREGISTRATION.md` 的共同掩码规则处理，默认全部计入。']
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return dict(paired_summary=summary_rows, decision=verdicts)
