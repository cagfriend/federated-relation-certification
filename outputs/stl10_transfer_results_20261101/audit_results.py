import json
from pathlib import Path
import tempfile
from experiments.stl10_transfer.run import check_environment,check_run,digest
from experiments.stl10_transfer.design import schedule,filename,plan
from experiments.stl10_transfer.report import reports
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/stl10_transfer/results_full'
env=json.loads((OUT/'environment.json').read_text(encoding='utf-8'));check_environment(env)
manifest=json.loads((OUT/'completed.json').read_text(encoding='utf-8'))
assert all(digest(OUT/p)==h for p,h in manifest['files'].items())
assert json.loads((OUT/'finished.json').read_text())['completed_manifest_sha256']==digest(OUT/'completed.json')
specs={s.case_id:s for s in plan('full',env['prepare_device'])};runs=[];groups={}
for meta in schedule('full'):
 marker=json.loads((OUT/f"prepared_{meta['partition']}_seed_{meta['seed']}.json").read_text())
 r=json.loads((OUT/'runs'/filename(meta)).read_text(encoding='utf-8'))
 check_run(r,meta,specs[meta['case_id']],Path(marker['path']),False)
 runs.append(r);groups.setdefault((r['partition'],r['seed'],r['case_id']),{})[r['method']]=r
keys=('head_digest_after_public','public_schedule_digest','public_optimizer_steps','student_forward_endpoints','public_edges_consumed','committed_counts_digest','received_counts_digests','private_loss','public_loss','private_subset_digest','private_samples_per_client','private_subset_pseudo_histograms','private_optimizer_steps','private_forward_endpoints','positive_relation_fraction','traffic')
for group in groups.values():
 b=group['B']
 for method in ('E','D'):
  r=group[method]
  assert r['initial_head_digest']==b['initial_head_digest'] and r['graph_sha256']==b['graph_sha256']
  assert [[q[k] for k in keys] for q in r['round_records']]==[[q[k] for k in keys] for q in b['round_records']]
  assert [{k:v for k,v in q.items() if k!='method'} for q in r['metrics']]==[{k:v for k,v in q.items() if k!='method'} for q in b['metrics']]
names=['report.md','summary.json','runs.csv','paired_cost.csv','paired_summary.csv','cross_M_ACC_sensitivity.csv']
with tempfile.TemporaryDirectory() as t:
 reports(t,runs,False,'full')
 assert all((Path(t)/n).read_bytes()==(OUT/n).read_bytes() for n in names)
bs=[r for r in runs if r['method']=='B'];clients=[c for r in bs for c in r['metrics'][-1]['clients']]
quality=dict(unique_configurations=len(bs),final_acc_range=[min(r['metrics'][-1]['mean']['acc'] for r in bs),max(r['metrics'][-1]['mean']['acc'] for r in bs)],final_nmi_range=[min(r['metrics'][-1]['mean']['nmi'] for r in bs),max(r['metrics'][-1]['mean']['nmi'] for r in bs)],client_cases=len(clients),one_cluster=sum(c['occupied_clusters']==1 for c in clients),dominant_at_least_99_percent=sum(c['largest_cluster_fraction']>=.99 for c in clients),dominant_fraction_min=min(c['largest_cluster_fraction'] for c in clients))
receipt=dict(status='passed',runs=len(runs),trajectory_blocks=len(groups),relation_comparisons=sum(r['validation']['relation_comparisons'] for r in runs),candidate_membership_comparisons=sum(r['validation']['candidate_membership_comparisons'] for r in runs),mismatches=sum(r['validation']['mismatches'] for r in runs),manifest_files_verified=len(manifest['files']),reports_byte_reproduced=names,quality=quality,completed_sha256=digest(OUT/'completed.json'))
(Path(__file__).parent/'AUDIT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(json.dumps(receipt,indent=2))
