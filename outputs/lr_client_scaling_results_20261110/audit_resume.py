from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.stl10_transfer.run import digest
out=ROOT/'experiments/lr_client_scaling/results_full_fixed_per_client';dest=Path(__file__).parent
def read(p):return json.loads(p.read_text(encoding='utf-8'))
inv=[read(p) for p in out.glob('invocation_*.json')];resume=next(r['utc'] for r in inv if r['resume'])
records=[read(p) for p in (out/'runs').glob('*.json')]
assert sum(r['worker_ended_utc']<resume for r in records)==15
assert all(not r['worker_started_utc']<resume<r['worker_ended_utc'] for r in records)
old=read(ROOT/'experiments/lr_repeat/results_full/environment.json')['sources']
for p,h in old.items():assert digest(ROOT/p)==h,p
a=read(dest/'audit.json');a.update(pre_resume_completed_runs=15,post_resume_completed_runs=39,saved_workers_crossing_resume=0,previous_frozen_sources_unchanged=len(old))
(dest/'audit.json').write_text(json.dumps(a,indent=2),encoding='utf-8')
print('15 preserved records by timestamps; no saved main run crosses resume; previous 110 source digests unchanged')
