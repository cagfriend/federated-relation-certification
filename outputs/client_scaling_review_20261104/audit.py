"""Independent post-smoke arithmetic, archive, and input checks."""
import csv
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.client_scaling.design import filename, schedule, plan
from experiments.client_scaling.run import verify_completed, verify_groups, non_time_rows, check_environment
from experiments.client_scaling.report import reports
from experiments.stl10_transfer.run import digest, check_run

out = Path(__file__).parent / 'smoke_final'
verify_completed(out)
env = json.loads((out / 'environment.json').read_text(encoding='utf-8'))
check_environment(env)
runs = [(m, json.loads((out / 'runs' / filename(m)).read_text(encoding='utf-8')))
        for m in schedule('smoke', 'all')]
memory = [(m, json.loads((out / 'memory' / filename(m)).read_text(encoding='utf-8')))
          for m in schedule('smoke', 'all', memory=True)]
assert len(verify_groups(runs)) == 8
by_identity = {filename(m): r for m, r in runs}
for m, r in memory:
    assert non_time_rows(r) == non_time_rows(by_identity[filename(m)])
with (out / 'runs.csv').open(encoding='utf-8') as f:
    for row in csv.DictReader(f):
        meta = dict(regime=row['regime'], clients=int(row['clients']), partition=row['partition'], seed=int(row['seed']), method=row['method'])
        r = by_identity[filename(meta)]
        s = r['summary'][meta['method']]
        assert float(row['final_acc']) == s['final_metrics']['mean']['acc']
        assert float(row['common_preparation_seconds']) == r['common_preparation_seconds'] > 0
        assert float(row['shared_loading_seconds']) == r['shared_loading_seconds'] > 0
        assert float(row['exchange_seconds']) == s['exchange_seconds']
        assert int(row['raw_communication_bytes']) == s['traffic']['total_bytes']
with (out / 'paired_cost.csv').open(encoding='utf-8') as f:
    for row in csv.DictReader(f):
        m = dict(regime=row['regime'], clients=int(row['clients']), partition=row['partition'], seed=int(row['seed']))
        d = by_identity[filename(dict(m, method='D'))]
        ref = row['comparison'][-1]
        b = by_identity[filename(dict(m, method=ref))]
        ds, bs = d['summary']['D'], b['summary'][ref]
        assert float(row['head_ratio']) == ds['head_pipeline_seconds'] / bs['head_pipeline_seconds']
        assert float(row['generation_saved_seconds']) == bs['generation_seconds'] - ds['generation_seconds']
        assert float(row['with_prep_loading_ratio']) == (d['common_preparation_seconds'] + d['shared_loading_seconds'] + ds['head_pipeline_seconds']) / (b['common_preparation_seconds'] + b['shared_loading_seconds'] + bs['head_pipeline_seconds'])
with (out / 'final_clients.csv').open(encoding='utf-8') as f:
    final_rows = list(csv.DictReader(f))
assert len(final_rows) == 72 and all(int(r['round']) == 3 for r in final_rows)
with (out / 'client_checkpoints.csv').open(encoding='utf-8') as f:
    assert len(list(csv.DictReader(f))) == 216
with (out / 'collapse_events.csv').open(encoding='utf-8') as f:
    assert all(r['single_cluster'] == 'True' or r['largest_cluster_at_least_099'] == 'True' for r in csv.DictReader(f))
with tempfile.TemporaryDirectory() as temporary:
    target = Path(temporary)
    reports(target, runs, memory, fixture=True)
    generated = sorted(p.name for p in target.iterdir())
    for name in generated:
        assert (target / name).read_bytes() == (out / name).read_bytes(), name
old_env = json.loads((ROOT / 'experiments/k_scaling/results_full/environment.json').read_text(encoding='utf-8'))
assert all(digest(ROOT / p) == h for p, h in old_env['sources'].items())
anchors = []
spec = plan('full', 'fixed_total')[1]
for seed in (1001, 1002, 1003):
    for part in ('iid', 'dirichlet_0.1'):
        marker = json.loads((ROOT / 'experiments/stl10_transfer/results_full' / f'prepared_{part}_seed_{seed}.json').read_text(encoding='utf-8'))
        base = Path(marker['path'])
        assert digest(base / 'prepared.json') == marker['metadata_sha256']
        anchor = json.loads((ROOT / 'experiments/stl10_compute/results_full/runs' / f'{part}_{spec.case_id}_seed_{seed}_B.json').read_text(encoding='utf-8'))
        check_run(anchor, dict(seed=seed, partition=part, method='B', case_id=spec.case_id), spec, base, False)
        anchors.append([seed, part])
result = dict(status='PASS', unit_tests=7, smoke_runs=len(runs), smoke_memory_runs=len(memory),
              triples=8, relation_comparisons=sum(r['validation']['relation_comparisons'] for _, r in runs),
              candidate_comparisons=sum(r['validation']['candidate_membership_comparisons'] for _, r in runs),
              final_client_rows=72, checkpoint_client_rows=216, reports_reproduced=generated,
              old_frozen_source_files_unchanged=len(old_env['sources']), compatible_historical_anchors=anchors,
              formal_training_started=False)
(Path(__file__).parent / 'audit.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result))
