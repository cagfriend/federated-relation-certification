"""User-confirmed sleep exclusion; preserve every raw result and pair common rounds."""
import copy, csv, json, statistics as st, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from experiments.public_scaling.util import load_json
from experiments.public_scaling.data import sha
from experiments.private_workload.design import spec_from_json
from experiments.private_workload.report import reports
HERE = Path(__file__).parent; OUT = ROOT / 'experiments/private_workload/results_full'; ADJUSTED = HERE / 'pause_adjusted'
MASK = {('dirichlet_0.1', 606): {150}, ('iid', 505): {143}}
EVENTS = [dict(partition='dirichlet_0.1', seed=606, case_id='m16384_fixed8_priv1024', method='B', round=150, phase='generation', raw_seconds=36.88578900002176),
          dict(partition='iid', seed=505, case_id='m16384_fixed8_priv2048', method='E', round=143, phase='public', raw_seconds=15.030995499982964)]
def median(v): return st.median(list(v))
def csvwrite(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def main():
    raw = HERE / 'audit_raw.json'
    if not raw.exists(): raw.write_bytes((HERE / 'audit.json').read_bytes())
    base = load_json(raw); env = load_json(OUT / 'environment.json'); done = load_json(OUT / 'completed.json')
    present = {p.name for p in OUT.iterdir() if p.is_file()}
    for name, h in done['files'].items():
        if name in present: assert sha(OUT / name) == h, name
    cases = []; profiles = []; costs = []; excluded = []; retained = []
    for seed in env['design']['seeds']:
        for part in env['design']['partitions']:
            specs = [spec_from_json(v) for v in env['plan']]; shift = seed % len(specs); specs = specs[shift:] + specs[:shift]
            for spec in specs:
                cid = spec.case_id
                path = OUT / f'{part}_{cid}_seed_{seed}.json'; original = load_json(path); c = copy.deepcopy(original); mask = MASK.get((part, seed), set())
                for m, s in c['summary'].items():
                    rows = [r for r in original['round_records'] if r['method'] == m and r['round'] not in mask]
                    removed = [r for r in original['round_records'] if r['method'] == m and r['round'] in mask]
                    assert len(rows) == 200 - len(mask) and len(removed) == len(mask)
                    for r in removed: excluded.append(dict(partition=part, seed=seed, case_id=cid, method=m, round=r['round'], reason='Common paired-round mask for user-confirmed process sleep; not a failure', **{p + '_seconds': r[p + '_seconds'] for p in ('private', 'generation', 'exchange', 'public', 'pipeline')}))
                    for phase in ('private', 'generation', 'exchange', 'public'): s[phase + '_seconds'] = sum(r[phase + '_seconds'] for r in rows)
                    s['head_pipeline_seconds'] = s['initialization_seconds'] + sum(r['pipeline_seconds'] for r in rows)
                    s['with_shared_preparation_seconds'] = c['common_preparation_seconds'] + c['shared_loading_seconds'] + s['head_pipeline_seconds']
                    s['generation_fraction'] = s['generation_seconds'] / s['head_pipeline_seconds']
                    retained.append(dict(partition=part, seed=seed, case_id=cid, method=m, training_rounds=200, timed_rounds=len(rows), excluded_rounds=','.join(map(str, sorted(mask)))))
                c['timing_filter'] = dict(reason='User confirmed the process slept (system sleep) during these rounds; exclude common rounds from all configurations/methods within each partition/seed', excluded_rounds=sorted(mask), training_rounds=200, timed_rounds=200 - len(mask), raw_case_sha256=sha(path), quality_coverage_and_workload_counters='Unchanged: all 200 trained rounds', initialization_and_C0='Retained once per original method/case')
                cases.append(c)
                for b in ('B', 'E'):
                    a, z = c['summary']['D'], c['summary'][b]
                    costs.append(dict(partition=part, seed=seed, case_id=cid, comparison='D/' + b,
                        **{p + '_ratio': a[p] / z[p] for p in ('generation_seconds', 'head_pipeline_seconds', 'with_shared_preparation_seconds')},
                        **{p + '_saved_seconds': z[p] - a[p] for p in ('generation_seconds', 'head_pipeline_seconds', 'with_shared_preparation_seconds')},
                        D_generation_fraction=a['generation_fraction'], reference_generation_fraction=z['generation_fraction'], D_teacher_recompute_fraction=a['teacher_recompute_fraction'], reference_teacher_recompute_fraction=z['teacher_recompute_fraction'], extra_persistent_bytes=a['persistent_method_array_bytes'] - z['persistent_method_array_bytes'], traffic_byte_difference=a['traffic']['total_bytes'] - z['traffic']['total_bytes']))
                if spec.private_limit is None:
                    for m in ('B', 'E', 'D'):
                        p = load_json(OUT / f'memory_{part}_{cid}_{m}_seed_{seed}.json'); profiles.append({k: v for k, v in p.items() if k not in ('identity', 'payload_sha256')})
    assert len(excluded) == 18 and sum(r['timed_rounds'] for r in retained) == 10800 - 18
    reports(ADJUSTED, cases, profiles)
    provenance = dict(user_confirmed_process_sleeps=EVENTS, not_fault_events=True, common_masks=[dict(partition=p, seed=s, excluded_rounds=sorted(v)) for (p, s), v in MASK.items()], method_round_times_excluded=18, raw_training_rounds_per_method=200, raw_files_unchanged=True, initialization_and_preparation_retained=True, imputation=False, scope='Only timing is filtered. Parameters, gradients, metrics, coverage, byte/workload counters and memory retain the original completed 200-round experiment.')
    (HERE / 'PAUSE_EXCLUSION.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
    csvwrite(HERE / 'excluded_round_timings.csv', excluded); csvwrite(HERE / 'retained_timing_rounds.csv', retained); csvwrite(HERE / 'paired_cost_adjusted.csv', costs)
    report = ADJUSTED / 'report.md'; report.write_text('> 主要统计已按用户确认的两次进程休眠剔除计时。强非IID seed606统一剔除r150，IID seed505统一剔除r143；各自全部档位/BED使用同一掩码。初始化/C0仍计，训练和质量指标保留全部200轮。原始计时未覆写，见上级PAUSE_EXCLUSION.json。休眠不计故障。\n\n' + report.read_text(encoding='utf-8'), encoding='utf-8')
    summary = []
    for part in env['design']['partitions']:
        for cid in sorted({r['case_id'] for r in costs}):
            for comp in ('D/B', 'D/E'):
                rr = [r for r in costs if (r['partition'], r['case_id'], r['comparison']) == (part, cid, comp)]
                summary.append(dict(partition=part, case_id=cid, comparison=comp, **{k: median(r[k] for r in rr) for k in rr[0] if k not in ('partition', 'seed', 'case_id', 'comparison')}, head_wins=sum(r['head_pipeline_seconds_ratio'] < 1 for r in rr), head_ratio_min=min(r['head_pipeline_seconds_ratio'] for r in rr), head_ratio_max=max(r['head_pipeline_seconds_ratio'] for r in rr)))
    effects = list(csv.DictReader((ADJUSTED / 'workload_effects.csv').read_text(encoding='utf-8').splitlines())); workload = []
    for part in env['design']['partitions']:
        for m in ('B', 'E', 'D'):
            for limit in (2048, 1024):
                ee = [e for e in effects if e['partition'] == part and e['method'] == m and int(e['private_limit']) == limit]
                workload.append(dict(partition=part, method=m, private_limit=limit, head_reduced_over_full_median=median(float(e['head_pipeline_seconds_reduced_over_full']) for e in ee), head_seconds_saved_median=median(float(e['head_pipeline_seconds_saved_seconds_full_minus_reduced']) for e in ee), with_preparation_reduced_over_full_median=median(float(e['with_shared_preparation_seconds_reduced_over_full']) for e in ee), generation_fraction_change_median=median(float(e['generation_fraction_change_reduced_minus_full']) for e in ee)))
    base.update(cost_summary=summary, workload_effects=workload, manual_pause_exclusion=provenance, all_original_timings_retained=True, all_original_timings_in_performance_statistics=False,
        scope='Known-seed paired serial CPU timing after user-confirmed process-sleep exclusion with common per-partition/seed round masks. Sleeps are not fault events. No raw data overwritten or times imputed.')
    base['raw_timing_audit'] = 'audit_raw.json'; base['primary_derived_reports'] = 'pause_adjusted/'
    (HERE / 'audit.json').write_text(json.dumps(base, indent=2), encoding='utf-8')
    hashes = {p.name: sha(p) for p in ADJUSTED.iterdir() if p.is_file() and p.name != 'MANIFEST.json'}
    (ADJUSTED / 'MANIFEST.json').write_text(json.dumps(dict(source_completed_sha256=sha(OUT / 'completed.json'), exclusion_sha256=sha(HERE / 'PAUSE_EXCLUSION.json'), files=hashes), indent=2), encoding='utf-8')
    for name, h in done['files'].items():
        if name in present: assert sha(OUT / name) == h, name
    print(json.dumps(dict(unchanged_raw_files=len(present), common_mask_method_rounds_excluded=len(excluded), cost_summary=summary, workload_effects=workload), indent=2))
if __name__ == '__main__': main()
