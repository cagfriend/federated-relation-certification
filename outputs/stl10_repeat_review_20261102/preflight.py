import hashlib
import json
from pathlib import Path
from experiments.stl10_repeat_confirmation.run import load_verified_anchors, frozen_sources
from experiments.stl10_repeat_confirmation.design import schedule, plan
from experiments.stl10_transfer.run import check_environment, digest, power_status
from experiments.public_scaling.head import Head
from experiments.public_scaling.engine import heads_digest
from experiments.public_scaling.graphs import make_graph

ROOT = Path.cwd()
OUT = ROOT / 'outputs/stl10_repeat_review_20261102'
def read(p):
    return json.loads(p.read_text(encoding='utf-8'))
remote = read(OUT / 'remote_files.json')
changed = []
for f in remote['files']:
    b = (ROOT / f['path']).read_bytes()
    if hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest() != f['sha']:
        changed.append(f['path'])
expected = {'experiments/stl10_repeat_confirmation/' + name for name in ('run.py', 'design.py', 'report.py', 'test_run.py')}
if set(changed) != expected:
    raise ValueError(dict(unexpected_source_changes=changed))
source = ROOT / 'experiments/stl10_transfer/results_full'
check_environment(read(source / 'environment.json'))
prepared = {}
spec = plan('full')[0]
for seed in (1001, 1002, 1003):
    for part in ('iid', 'dirichlet_0.1'):
        m = read(source / f'prepared_{part}_seed_{seed}.json')
        if digest(Path(m['path']) / 'prepared.json') != m['metadata_sha256']:
            raise ValueError('Cache metadata changed')
        prepared[f'{seed}|{part}'] = m
env = dict(source_results=str(source), prepared=prepared,
           anchor_results=str(ROOT / 'experiments/stl10_longrun/results_full'),
           compute_results=str(ROOT / 'experiments/stl10_compute/results_full'))
a8, al, ac = load_verified_anchors(env)
if (len(a8), len(al), len(ac)) != (6, 4, 6):
    raise ValueError('Expected 16 historical anchors')
for (seed, part), r in a8.items():
    initial = heads_digest([Head(w, spec.config.classes, seed, c) for c, w in enumerate(spec.config.dimensions)])
    graph = hashlib.sha256(make_graph(spec.config.samples, spec.config.degree, seed).astype('<u4').tobytes()).hexdigest()
    if initial != r['initial_head_digest'] or graph != r['graph_sha256']:
        raise ValueError('Initial heads or graph differs')
receipt = dict(result='PASS', commit=remote['commit'], remote_files_verified=len(remote['files']),
               local_changes=changed, old_experiment_sources_unchanged=True,
               prepared_metadata_verified=6, historical_anchors_verified=dict(transfer=6,longrun=4,compute=6),
               current_source_sha256=frozen_sources(), planned_runs=len(schedule('full')),
               power_snapshot=power_status(), formal_experiment_started=False,
               note='Cache metadata and historical seals checked; worker fully verifies official source assets and cache files before training.')
(OUT / 'preflight.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print('PASS: 6 cache markers, 16 historical anchors, 54 scheduled runs; no formal run started.')
