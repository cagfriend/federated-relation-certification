"""Recheck smoke artifacts, deterministic reports and unchanged historical sources."""
import hashlib
import json
import tempfile
from pathlib import Path
from experiments.stl10_transfer.run import check_environment, check_run, digest
from experiments.stl10_transfer.design import schedule, filename, plan
from experiments.stl10_transfer.report import reports
from experiments.perf_confirmation.run import check_environment as historical_check

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'experiments/stl10_transfer/results_smoke_final'
env = json.loads((OUT / 'environment.json').read_text(encoding='utf-8'))
check_environment(env)
manifest = json.loads((OUT / 'completed.json').read_text(encoding='utf-8'))
assert all(digest(OUT / p) == h for p, h in manifest['files'].items())
finished = json.loads((OUT / 'finished.json').read_text(encoding='utf-8'))
assert finished['completed_manifest_sha256'] == digest(OUT / 'completed.json')
specs = {s.case_id:s for s in plan('smoke',env['prepare_device'])}
runs=[]
for m in schedule('smoke'):
    marker=json.loads((OUT/f"prepared_{m['partition']}_seed_{m['seed']}.json").read_text(encoding='utf-8'))
    r=json.loads((OUT/'runs'/filename(m)).read_text(encoding='utf-8'))
    check_run(r,m,specs[m['case_id']],Path(marker['path']),True)
    runs.append(r)
report_names=['report.md','summary.json','runs.csv','paired_cost.csv','paired_summary.csv','cross_M_ACC_sensitivity.csv']
with tempfile.TemporaryDirectory() as t:
    reports(t,runs,fixture=True,preset='smoke')
    assert all((Path(t)/n).read_bytes()==(OUT/n).read_bytes() for n in report_names)
historical_check(json.loads((ROOT/'experiments/perf_confirmation/results_full/environment.json').read_text(encoding='utf-8')))
assert manifest['count']==12 and manifest['blocks_verified']==4
assert manifest['mismatches']==0 and manifest['relation_comparisons']==2880 and manifest['candidate_membership_comparisons']==3840
receipt=dict(status='passed',runs_checked=12,triples_checked=4,relation_comparisons=2880,candidate_membership_comparisons=3840,mismatches=0,report_files_byte_reproduced=report_names,historical_sources_unchanged=True,completed_manifest_sha256=digest(OUT/'completed.json'),source_hashes=env['source_hashes'],scope='synthetic fixture only; no official training launched')
(Path(__file__).parent/'AUDIT.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in receipt.items() if k!='source_hashes'},indent=2))
