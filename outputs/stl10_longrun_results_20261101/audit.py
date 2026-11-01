"""Read-only audit of formal results, writing only a separate audit directory."""
import hashlib
import json
import math
import tempfile
from pathlib import Path
import numpy as np
from experiments.stl10_longrun.run import check_environment, check_run, check_anchor, load_anchor, digest
from experiments.stl10_longrun.design import schedule, filename, plan
from experiments.stl10_longrun.report import reports
from experiments.stl10_transfer.run import check_run as check_old_run
from experiments.stl10_transfer.design import plan as old_plan
from experiments.private_workload.student import selected_edges, schedule_digest
from experiments.public_scaling.graphs import make_graph

ROOT = Path.cwd()
OUT = ROOT / 'outputs/stl10_longrun_results_20261101'
RESULT = ROOT / 'experiments/stl10_longrun/results_full'
def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def require(ok, message):
    if not ok:
        raise ValueError(message)
def near(a, b):
    return math.isfinite(a) and math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)

env = read(RESULT / 'environment.json')
final_env = read(RESULT / 'environment_final.json')
check_environment(env)
check_environment(final_env)
require(all(final_env[k] == v for k, v in env.items()), 'Final environment changed original fields')
done = read(RESULT / 'completed.json')
finished = read(RESULT / 'finished.json')
require(finished['status'] == 'complete' and finished['completed_runs'] == finished['expected_runs'] == done['count'] == 8, 'Completion count mismatch')
require(digest(RESULT / 'completed.json') == finished['completed_manifest_sha256'], 'Completion manifest seal differs')
actual = {str(p.relative_to(RESULT)) for p in RESULT.rglob('*') if p.is_file() and p.name not in ('completed.json', 'finished.json', 'ARCHIVED_RAW.md')}
require(actual == set(done['files']), 'Manifest coverage differs')
for p, expected in done['files'].items():
    require(digest(RESULT / p) == expected, f'Manifest hash differs: {p}')

metas = schedule('full')
require({p.name for p in (RESULT / 'runs').glob('*.json')} == {filename(m) for m in metas}, 'Run matrix differs')
expected_checkpoints = [0, 1, 2, 5, 10] + list(range(20, 201, 20))
runs, rows, events = [], [], []
for meta in metas:
    r = read(RESULT / 'runs' / filename(meta))
    spec = next(s for s in plan('full') if s.steps == meta['steps'])
    cfg = spec.config
    cache_marker = env['prepared'][f"{meta['seed']}|{meta['partition']}"]
    prepared = Path(cache_marker['path'])
    require(digest(prepared / 'prepared.json') == cache_marker['metadata_sha256'], 'Cache metadata changed')
    check_run(r, meta, spec, prepared)
    anchor = load_anchor(env['source_results'], meta['partition'], meta['seed'])
    old_spec = old_plan('full')[-1]
    check_old_run(anchor, dict(seed=meta['seed'], partition=meta['partition'], method='B', case_id=old_spec.case_id), old_spec, prepared, False)
    check_anchor(r, anchor)
    require(r['dataset'] == 'STL-10' and r['rounds'] == 200 and r['steps'] == meta['steps'], 'Run identity differs')
    require([q['round'] for q in r['checkpoints']] == expected_checkpoints, 'Checkpoint coverage differs')
    edges = make_graph(cfg.samples, cfg.degree, meta['seed'])
    for row in r['round_records']:
        require(row['method'] == 'B', 'Method differs')
        require(row['public_edges_consumed'] == 6 * meta['steps'] * 256, 'Public edge budget differs')
        require(row['student_forward_endpoints'] == 12 * meta['steps'] * 256, 'Student forward budget differs')
        require(row['teacher_forward_endpoints'] == 6 * 16384, 'Full teacher budget differs')
        require(row['private_samples_per_client'] == [834, 834, 833, 833, 833, 833], 'Private sample counts differ')
        require(row['private_optimizer_steps'] == 42 and row['private_forward_endpoints'] == 5000, 'Private work budget differs')
        require(near(row['positive_relation_fraction'] * 6 * len(edges), round(row['positive_relation_fraction'] * 6 * len(edges))), 'Relation mean is not a full graph bit count')
        require(all(x == row['committed_counts_digest'] for x in row['received_counts_digests']), 'Client targets differ')
        orders = [selected_edges(spec, meta['seed'], c, row['round']) for c in range(6)]
        require(schedule_digest(orders) == row['public_schedule_digest'], 'Student edge schedule differs')
    reconstructed_events = []
    for q in r['checkpoints']:
        cs = q['clients']
        require(len(cs) == 6 and [c['client'] for c in cs] == list(range(6)), 'Checkpoint client coverage differs')
        for c, width in zip(cs, cfg.dimensions):
            counts = c['cluster_counts']
            require(c['width'] == width and len(counts) == 10 and sum(counts) == 8000 and all(isinstance(x, int) and x >= 0 for x in counts), 'Cluster counts invalid')
            require(c['occupied_clusters'] == sum(x > 0 for x in counts) and near(c['largest_cluster_fraction'], max(counts) / 8000), 'Occupancy statistic differs')
            require(all(math.isfinite(c[k]) for k in ('acc', 'nmi', 'ari')), 'Nonfinite quality metric')
        for k in ('acc', 'nmi', 'ari'):
            require(near(q['mean'][k], float(np.mean([c[k] for c in cs]))), 'Mean quality statistic differs')
        single = sum(c['occupied_clusters'] == 1 for c in cs)
        dominant = sum(c['largest_cluster_fraction'] >= .99 for c in cs)
        require(single == q['single_cluster_clients'] and dominant == q['dominant_99_clients'], 'Event counts differ')
        require(near(q['mean_largest_cluster_fraction'], float(np.mean([c['largest_cluster_fraction'] for c in cs]))), 'Mean largest fraction differs')
        require(0 <= q['private_pseudo_fit_mean'] <= 1, 'Private fit invalid')
        if q['round']:
            require(q['teacher_edge_fraction'] == r['round_records'][q['round'] - 1]['positive_relation_fraction'], 'Checkpoint teacher fraction differs')
        if single or dominant:
            reconstructed_events.append(dict(round=q['round'], single_cluster_clients=single, dominant_99_clients=dominant, warning_only=q['round'] < 20))
            events.append(dict(**meta, round=q['round'], single_clients=[c['client'] for c in cs if c['occupied_clusters'] == 1], dominant_99_clients=[c['client'] for c in cs if c['largest_cluster_fraction'] >= .99], mean_largest=q['mean_largest_cluster_fraction']))
    require(reconstructed_events == r['events'], 'Event log differs')
    final = r['checkpoints'][-1]
    own = dict(S1=final['single_cluster_clients'] == 0 and all(c['largest_cluster_fraction'] < .99 for c in final['clients']) and final['mean_largest_cluster_fraction'] <= .6,
               S2=all(q['single_cluster_clients'] <= 2 and q['mean_largest_cluster_fraction'] < .9 for q in r['checkpoints'] if q['round'] >= 20),
               Q1=final['mean']['acc'] >= .14 and final['mean']['nmi'] >= .01,
               Q2=r['round_records'][-1]['positive_relation_fraction'] <= .6)
    own['passed'] = all(own.values())
    for phase in ('private', 'generation', 'exchange', 'public'):
        require(near(r['summary']['B'][phase + '_seconds'], sum(x[phase + '_seconds'] for x in r['round_records'])), 'Timing summary differs')
    require(near(r['summary']['B']['head_pipeline_seconds'], r['summary']['B']['initialization_seconds'] + sum(x['pipeline_seconds'] for x in r['round_records'])), 'Head pipeline differs')
    rows.append(dict(**meta, **own, final_metrics=final['mean'], final_mean_largest=final['mean_largest_cluster_fraction'], final_max_client_largest=max(c['largest_cluster_fraction'] for c in final['clients']), final_edge_fraction=r['round_records'][-1]['positive_relation_fraction'], final_private_fit=final['private_pseudo_fit_mean'], historical_step8_metrics=anchor['metrics'][-1]['mean']))
    runs.append((meta, r))
    print('PASS', filename(meta), flush=True)

with tempfile.TemporaryDirectory() as tmp:
    regenerated = reports(tmp, runs, fixture=False, preset='full')
    for f in ('report.md', 'verdict.json'):
        require((Path(tmp) / f).read_bytes() == (RESULT / f).read_bytes(), f'Regenerated report differs: {f}')
require(all(row[k] == v[k] for row, v in zip(rows, regenerated['trajectories']) for k in ('S1', 'S2', 'Q1', 'Q2', 'passed')), 'Independent criteria differ')
selected = 2 if all(x['passed'] for x in rows if x['steps'] == 2) else (1 if all(x['passed'] for x in rows if x['steps'] == 1) else None)
require(selected == regenerated['selected_steps'] == done['selected_steps'], 'Independent selection differs')
invocations = [read(p) for p in sorted(RESULT.glob('invocation_*.json'))]
audit = dict(result='PASS', manifest_files_verified=len(done['files']), source_hashes_verified=len(env['source_hashes']), trajectories=8, rounds_per_trajectory=200, checkpoints_per_trajectory=15, client_checkpoints=8*15*6, independent_selected_steps=selected, rows=rows, observed_events=events, invocations=invocations, started_power=env['started_power'], ended_power=final_env['ended_power'], caveat='Power snapshots only; checkpoint events only. B-only quality experiment, no certification performance claims.', interruption='User-requested manual stop; not counted as a fault. Completed trajectory seals are retained; unfinished trajectory restarted.')
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(result='PASS', manifest_files_verified=len(done['files']), selected_steps=selected, events=events), ensure_ascii=False), flush=True)
