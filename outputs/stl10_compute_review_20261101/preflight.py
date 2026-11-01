import hashlib
import json
from pathlib import Path
from experiments.stl10_compute.run import frozen_sources, load_verified_anchors
from experiments.stl10_compute.design import plan, schedule
from experiments.stl10_transfer.run import check_environment, digest, power_status
from experiments.stl10_transfer.data import verify
from experiments.public_scaling.head import Head
from experiments.public_scaling.engine import heads_digest
from experiments.public_scaling.graphs import make_graph

ROOT = Path.cwd()
OUT = ROOT / 'outputs/stl10_compute_review_20261101'
source = ROOT / 'experiments/stl10_transfer/results_full'
long_source = ROOT / 'experiments/stl10_longrun/results_full'
def read(p):
    return json.loads(p.read_text(encoding='utf-8'))
remote = read(OUT / 'remote_files.json')
changed = []
for f in remote['files']:
    b = (ROOT / f['path']).read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
    if actual != f['sha']:
        changed.append(f['path'])
if set(changed) != {'experiments/stl10_compute/run.py', 'experiments/stl10_compute/test_run.py'}:
    raise ValueError(dict(unexpected_source_differences=changed))
env_old = read(source / 'environment.json')
check_environment(env_old)
spec = plan('full')[0]
prepared = {}
for seed in (1001, 1002, 1003):
    for part in ('iid', 'dirichlet_0.1'):
        entry = read(source / f'prepared_{part}_seed_{seed}.json')
        p = Path(entry['path'])
        if digest(p / 'prepared.json') != entry['metadata_sha256']:
            raise ValueError('Cache metadata changed')
        print('Checking full cache:', seed, part, flush=True)
        verify(p, spec.config, seed, part, fixture=False)
        prepared[f'{seed}|{part}'] = entry
env = dict(source_results=str(source), anchor_results=str(long_source), prepared=prepared, fixture=False)
anchors8, anchors_long = load_verified_anchors(env)
if len(anchors8) != 6 or len(anchors_long) != 4:
    raise ValueError('Expected six original and four longrun anchors')
for (seed, part), record in anchors8.items():
    initial = heads_digest([Head(w, spec.config.classes, seed, c) for c, w in enumerate(spec.config.dimensions)])
    graph = hashlib.sha256(make_graph(spec.config.samples, spec.config.degree, seed).astype('<u4').tobytes()).hexdigest()
    if record['initial_head_digest'] != initial or record['graph_sha256'] != graph:
        raise ValueError('Current initial heads or graph differ from history')
receipt = dict(result='PASS', remote_commit=remote['commit'], remote_source_files_verified=len(remote['files']),
               local_source_corrections=changed, all_old_experiment_sources_unchanged=True,
               official_caches_verified=6, original_8step_anchors_verified=6,
               longrun_2step_anchors_verified=4, planned_runs=len(schedule('full')),
               current_source_sha256=frozen_sources(), power_snapshot=power_status(),
               formal_experiment_started=False)
(OUT / 'preflight.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print('Preflight PASS: six caches, six original anchors, four longrun anchors; no formal run started.', flush=True)
