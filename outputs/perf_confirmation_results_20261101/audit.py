import sys,json,tempfile,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R));H=Path(__file__).parent;O=R/'experiments/perf_confirmation/results_full'
from experiments.perf_confirmation.run import check_environment,check_run
from experiments.perf_confirmation.design import schedule,spec_from_json
from experiments.perf_confirmation.engine import check_block_identity
from experiments.perf_confirmation.report import reports
from experiments.public_scaling.data import sha
from experiments.public_scaling.util import load_json
env=load_json(O/'environment.json');done=load_json(O/'completed.json');check_environment(env);runs=[];hashes={};flags=[]
for name,h in done['files'].items():assert sha(O/name)==h
for meta in schedule('full'):
 from experiments.perf_confirmation.design import run_filename
 p=O/'runs'/run_filename(meta);r=load_json(p);hashes[p.relative_to(R).as_posix()]=sha(p)
 s=next(spec_from_json(s) for s in env['plan'] if spec_from_json(s).case_id==meta['case_id']);marker=load_json(O/f"prepared_{meta['partition']}_seed_{meta['seed']}.json");directory=Path(marker['path']);assert sha(directory/'prepared.json')==marker['metadata_sha256']
 check_run(r,s,meta['partition'],meta['seed'],env,directory,meta);runs.append(r)
 for key in ('private_seconds','generation_seconds','public_seconds'):
  med=statistics.median(x[key] for x in r['round_records'])
  for row in r['round_records']:
   if row[key]>max(1.,10*med):flags.append(dict(file=p.name,round=row['round'],phase=key,seconds=row[key],median=med))
keys={(r['partition'],r['seed'],r['case_id']) for r in runs}
for key in keys:check_block_identity([r for r in runs if (r['partition'],r['seed'],r['case_id'])==key])
with tempfile.TemporaryDirectory(dir=H) as t:
 reports(Path(t),runs,dict(blocks_checked=12,mismatches=0),expected_seeds=3)
 for p in Path(t).iterdir():assert p.read_bytes()==(O/p.name).read_bytes(),p.name
(H/'audit.json').write_text(json.dumps(dict(runs=72,blocks=12,mismatches=0,top_level_hashes=len(done['files']),run_sha256=hashes,reports_byte_identical=True,timing_flags=flags,rounds_excluded=0),indent=2),encoding='utf-8');print(json.dumps(flags,indent=2))

