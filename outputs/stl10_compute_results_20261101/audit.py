"""Read-only result audit; derived files go outside the experiment results."""
import json
import math
import statistics as st
import tempfile
from pathlib import Path

from experiments.stl10_compute.design import plan, schedule, filename
from experiments.stl10_compute.run import check_environment, check_run, check_anchor8, load_verified_anchors, verify_triples, TRAJECTORY_KEYS
from experiments.stl10_compute.report import reports, aggregate, guardrail_rows
from experiments.stl10_transfer.run import digest
from experiments.private_workload.student import selected_edges, schedule_digest

ROOT = Path.cwd()
RESULT = ROOT / 'experiments/stl10_compute/results_full'
OUT = ROOT / 'outputs/stl10_compute_results_20261101'
def read(p):
    return json.loads(p.read_text(encoding='utf-8'))
def require(ok, message):
    if not ok:
        raise ValueError(message)
def near(a, b):
    return math.isfinite(a) and math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-9)

env, final_env = read(RESULT / 'environment.json'), read(RESULT / 'environment_final.json')
check_environment(env)
check_environment(final_env)
require(all(final_env[k] == v for k, v in env.items()), 'Original environment fields changed')
preflight = read(ROOT / 'outputs/stl10_compute_review_20261101/preflight.json')
require(preflight['current_source_sha256'] == env['source_hashes'], 'Source differs from approved local corrections')
done, finished = read(RESULT / 'completed.json'), read(RESULT / 'finished.json')
require(finished['status'] == 'complete' and finished['expected_runs'] == finished['completed_runs'] == done['count'] == 18, 'Completion count differs')
require(digest(RESULT / 'completed.json') == finished['completed_manifest_sha256'], 'Completion manifest seal differs')
actual = {str(p.relative_to(RESULT)) for p in RESULT.rglob('*') if p.is_file() and p.name not in ('finished.json', 'completed.json', 'ARCHIVED_RAW.md')}
require(actual == set(done['files']), 'Manifest coverage differs')
for path, expected in done['files'].items():
    require(digest(RESULT / path) == expected, f'Manifest hash differs: {path}')
spec = plan('full')[0]
metas = schedule('full')
require({p.name for p in (RESULT / 'runs').glob('*.json')} == {filename(m) for m in metas}, 'Run matrix differs')
for entry in env['prepared'].values():
    require(digest(Path(entry['path']) / 'prepared.json') == entry['metadata_sha256'], 'Cache metadata changed')
anchors8, anchors_long = load_verified_anchors(env)
require(len(anchors8) == 6 and len(anchors_long) == 4, 'Anchor matrix differs')
completed, guards, timing_flags = [], [], []
for meta in metas:
    r = read(RESULT / 'runs' / filename(meta))
    prepared = Path(env['prepared'][f"{meta['seed']}|{meta['partition']}"]['path'])
    check_run(r, meta, spec, prepared, False)
    check_anchor8(r, anchors8[meta['seed'], meta['partition']])
    rr, summary = r['round_records'], r['summary'][meta['method']]
    require(r['dataset'] == 'STL-10', 'Dataset differs')
    for row in rr:
        require(row['method'] == meta['method'], 'Round method differs')
        require(row['private_samples_per_client'] == [834, 834, 833, 833, 833, 833], 'Private samples differ')
        require(row['private_optimizer_steps'] == 42 and row['private_forward_endpoints'] == 5000, 'Private workload differs')
        require(row['public_optimizer_steps'] == 12 and row['public_edges_consumed'] == 3072 and row['student_forward_endpoints'] == 6144, 'Public workload differs')
        orders = [selected_edges(spec, meta['seed'], c, row['round']) for c in range(6)]
        require(schedule_digest(orders) == row['public_schedule_digest'], 'Student edge schedule differs')
        require(all(x == row['committed_counts_digest'] for x in row['received_counts_digests']), 'Received target differs')
        require(math.isfinite(row['private_loss']) and math.isfinite(row['public_loss']), 'Nonfinite loss')
    for phase in ('private', 'generation', 'exchange', 'public'):
        values = [x[phase + '_seconds'] for x in rr]
        require(near(summary[phase + '_seconds'], sum(values)), 'Phase timing summary differs')
        # A diagnostic flag, never an automatic reason for exclusion.
        considered = rr[1:] if phase == 'generation' else rr
        median = st.median(x[phase + '_seconds'] for x in considered)
        for x in considered:
            if x[phase + '_seconds'] > max(2.0, 10 * median):
                timing_flags.append(dict(**meta, round=x['round'], phase=phase, seconds=x[phase + '_seconds'], median=median))
    require(near(summary['head_pipeline_seconds'], summary['initialization_seconds'] + sum(x['pipeline_seconds'] for x in rr)), 'Head pipeline differs')
    require(near(summary['with_shared_preparation_seconds'], r['common_preparation_seconds'] + r['shared_loading_seconds'] + summary['head_pipeline_seconds']), 'Shared preparation total differs')
    require(near(summary['generation_fraction'], summary['generation_seconds'] / summary['head_pipeline_seconds']), 'Generation fraction differs')
    recompute = sum(x['teacher_forward_endpoints'] for x in rr[1:]) / (199 * 6 * 16384)
    require(near(summary['teacher_recompute_fraction'], recompute), 'Teacher recompute fraction differs')
    for field in ('public_optimizer_steps', 'student_forward_endpoints', 'private_optimizer_steps', 'private_forward_endpoints'):
        require(summary[field] == sum(x[field] for x in rr), 'Count summary differs: ' + field)
    require([q['round'] for q in r['metrics']] == list(range(20, 201, 20)), 'Evaluation coverage differs')
    for q in r['metrics']:
        cs = q['clients']
        require(len(cs) == 6 and [c['client'] for c in cs] == list(range(6)), 'Client coverage differs')
        for c in cs:
            counts = c['cluster_counts']
            require(len(counts) == 10 and sum(counts) == 8000 and all(isinstance(n, int) and n >= 0 for n in counts), 'Cluster counts invalid')
            require(c['occupied_clusters'] == sum(n > 0 for n in counts) and near(c['largest_cluster_fraction'], max(counts) / 8000), 'Cluster statistic differs')
        for metric in ('acc', 'nmi', 'ari'):
            require(near(q['mean'][metric], st.mean(c[metric] for c in cs)), 'Mean evaluation differs')
    if meta['method'] == 'B':
        last = r['metrics'][-1]
        cs = last['clients']
        own = dict(S1=all(c['occupied_clusters'] >= 2 and c['largest_cluster_fraction'] < .99 for c in cs) and st.mean(c['largest_cluster_fraction'] for c in cs) <= .6,
                   S2=all(sum(c['occupied_clusters'] == 1 for c in q['clients']) <= 2 and st.mean(c['largest_cluster_fraction'] for c in q['clients']) < .9 for q in r['metrics']),
                   Q1=last['mean']['acc'] >= .14 and last['mean']['nmi'] >= .01,
                   Q2=rr[-1]['positive_relation_fraction'] <= .6)
        own['passed'] = all(own.values())
        guards.append(dict(partition=meta['partition'], seed=meta['seed'], **own))
    completed.append((meta, r))
    print('PASS', filename(meta), flush=True)

triples = verify_triples(completed, anchors_long, fixture=False)
require(len(triples) == done['triples_verified'] == 6, 'Triple coverage differs')
records = [r for _, r in completed]
relations = sum(r['validation']['relation_comparisons'] for r in records)
candidates = sum(r['validation']['candidate_membership_comparisons'] for r in records)
require(relations == done['relation_comparisons'] == 176947200 and candidates == done['candidate_membership_comparisons'] == 235929600 and done['mismatches'] == 0, 'Oracle coverage differs')
with tempfile.TemporaryDirectory() as tmp:
    reports(tmp, records, fixture=False, preset='full')
    for p in Path(tmp).iterdir():
        require(p.read_bytes() == (RESULT / p.name).read_bytes(), 'Regenerated report differs: ' + p.name)
rows, pairs, summaries = aggregate(records)
reported_guards = guardrail_rows(records)
for g in guards:
    other = next(v for v in reported_guards if v['partition'] == g['partition'] and v['seed'] == g['seed'])
    require(all(g[k] == other[k] for k in ('S1', 'S2', 'Q1', 'Q2', 'passed')), 'Independent guardrail differs')
groups = {(r['partition'], r['seed'], r['method']): r for r in rows}
for pair in pairs:
    d = groups[pair['partition'], pair['seed'], 'D']
    b = groups[pair['partition'], pair['seed'], pair['comparison'][-1]]
    require(near(pair['head_ratio'], d['head_pipeline_seconds'] / b['head_pipeline_seconds']) and near(pair['saved_seconds'], b['head_pipeline_seconds'] - d['head_pipeline_seconds']), 'Independent paired timing differs')

resources = []
for part in ('iid', 'dirichlet_0.1'):
    group = [r for r in rows if r['partition'] == part]
    resources.append(dict(partition=part,
                          B_generation_fraction_median=st.median(r['generation_fraction'] for r in group if r['method'] == 'B'),
                          E_recompute_fraction_median=st.median(r['teacher_recompute_fraction'] for r in group if r['method'] == 'E'),
                          D_recompute_fraction_median=st.median(r['teacher_recompute_fraction'] for r in group if r['method'] == 'D'),
                          D_over_B_peak_ratio_median=st.median(groups[part, s, 'D']['process_peak_bytes'] / groups[part, s, 'B']['process_peak_bytes'] for s in (1001,1002,1003)),
                          D_over_E_peak_ratio_median=st.median(groups[part, s, 'D']['process_peak_bytes'] / groups[part, s, 'E']['process_peak_bytes'] for s in (1001,1002,1003)),
                          D_minus_B_persistent_MiB=(groups[part,1001,'D']['persistent_method_array_bytes'] - groups[part,1001,'B']['persistent_method_array_bytes']) / 2**20))
for (part, seed), group in triples.items():
    require(len({r['summary'][m]['traffic']['total_bytes'] for m, r in group.items()}) == 1, 'Communication differs')
    require(group['D']['summary']['D']['persistent_method_array_bytes'] == group['E']['summary']['E']['persistent_method_array_bytes'], 'D/E persistent memory differs')
power = dict(start=env['started_power'], end=final_env['ended_power'], invocations=[read(p) for p in sorted(RESULT.glob('invocation_*.json'))], continuous_monitoring=False)
receipt = dict(result='PASS', manifest_files_verified=len(done['files']), source_hashes_verified=len(env['source_hashes']), runs=18, triples=6, rounds_per_run=200,
               verified_old_anchors=6, verified_longrun_anchors=4, oracle_relations=relations, oracle_candidate_memberships=candidates,
               mismatches=0, recorded_oracle_counts_only=True, replayed_all_training=False,
               guards=guards, pairs=pairs, paired_summary=summaries, resources=resources, timing_flags=timing_flags, power=power,
               note='No timing data excluded. One execution per method; no technical repeats. Process peak includes audit/evaluation; head time excludes them.')
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'audit.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(result='PASS', manifest_files_verified=len(done['files']), resources=resources, timing_flags=timing_flags), ensure_ascii=False), flush=True)
