import hashlib
import json
from dataclasses import replace
from pathlib import Path
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.stl10_longrun.design import plan, schedule
from experiments.stl10_longrun.engine import run as new_run
from experiments.stl10_longrun.run import load_anchor, digest, PRIVATE_ANCHOR_FIELDS
from experiments.stl10_transfer.engine import run as reference_run
from experiments.stl10_transfer.run import check_environment, check_run, power_status
from experiments.stl10_transfer.data import verify
from experiments.stl10_transfer.design import plan as transfer_plan
from experiments.public_scaling.head import Head
from experiments.public_scaling.engine import heads_digest
from experiments.public_scaling.graphs import make_graph

ROOT = Path.cwd()
OUT = ROOT / 'outputs/stl10_longrun_review_20261101'
remote = json.loads((OUT / 'remote_files.json').read_text(encoding='utf-8'))
compared, missing, different = [], [], []
for f in remote['files']:
    p = ROOT / f['path']
    if not p.exists():
        missing.append(f['path'])
        continue
    b = p.read_bytes()
    actual = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
    if actual != f['sha']:
        different.append(f['path'])
    compared.append(f['path'])
if missing or different:
    raise ValueError(dict(missing=missing, different=different))
print('Remote source bytes identical:', len(compared), flush=True)

# The new orchestration must reproduce the old B engine, including all
# non-timing round fields and metrics. Smoke data do not establish quality.
smoke = OUT / 'smoke'
smoke_env = json.loads((smoke / 'environment.json').read_text(encoding='utf-8'))
equivalence = []
with threadpool_limits(limits=1):
    for partition in ('iid', 'dirichlet_0.1'):
        cache = Path(smoke_env['prepared'][f'1001|{partition}']['path'])
        for spec in plan('smoke'):
            current = json.loads((smoke / 'runs' / f'{partition}_{spec.case_id}_seed_1001_B.json').read_text(encoding='utf-8'))
            old = reference_run(cache, spec, 'B', fixture=True)
            for a, b in zip(current['round_records'], old['round_records']):
                aa = {k: v for k, v in a.items() if not k.endswith('_seconds')}
                bb = {k: v for k, v in b.items() if not k.endswith('_seconds')}
                if aa != bb:
                    raise ValueError(f'Engine row differs: {partition}, {spec.steps}, {a["round"]}')
            by_round = {q['round']: q for q in old['metrics']}
            for q in current['checkpoints']:
                if q['round'] and (q['clients'] != by_round[q['round']]['clients'] or q['mean'] != by_round[q['round']]['mean']):
                    raise ValueError('Checkpoint differs from original evaluation')
            if current['initial_head_digest'] != old['initial_head_digest'] or current['summary']['B']['final_head_digest'] != old['summary']['B']['final_head_digest']:
                raise ValueError('Engine initial/final digest differs')
            equivalence.append(dict(partition=partition, steps=spec.steps, exact_rounds=len(old['round_records'])))
            print('Reference engine exact:', partition, spec.steps, flush=True)

source = ROOT / 'experiments/stl10_transfer/results_full'
environment = json.loads((source / 'environment.json').read_text(encoding='utf-8'))
check_environment(environment)
spec = plan('full')[0]
historical_spec = transfer_plan('full')[-1]
if spec.config.json() != historical_spec.config.json():
    raise ValueError('Long-run config differs from original full config')
anchors = []
for seed in (1002, 1003):
    for part in ('iid', 'dirichlet_0.1'):
        marker = json.loads((source / f'prepared_{part}_seed_{seed}.json').read_text(encoding='utf-8'))
        cache = Path(marker['path'])
        if digest(cache / 'prepared.json') != marker['metadata_sha256']:
            raise ValueError('Metadata mismatch')
        print('Verifying full cache:', seed, part, flush=True)
        verify(cache, spec.config, seed, part, fixture=False)
        anchor = load_anchor(source, part, seed)
        check_run(anchor, dict(seed=seed, partition=part, method='B', case_id=historical_spec.case_id), historical_spec, cache, False)
        initial = heads_digest([Head(width, spec.config.classes, seed, i) for i, width in enumerate(spec.config.dimensions)])
        graph = hashlib.sha256(make_graph(spec.config.samples, spec.config.degree, seed).astype('<u4').tobytes()).hexdigest()
        if initial != anchor['initial_head_digest'] or graph != anchor['graph_sha256']:
            raise ValueError('Initial head/graph differs from historical B')
        item = dict(seed=seed, partition=part, cache=str(cache), metadata_sha256=marker['metadata_sha256'], initial_head_digest=initial, graph_sha256=graph)
        anchors.append(item)
        print('Cache and initial anchor verified:', seed, part, flush=True)

power = power_status()
if power['ac_line_status'] != 1:
    raise RuntimeError('AC power is required before formal launch')
receipt = dict(commit=remote['commit'], source_files_verified=len(compared), smoke_original_engine_equivalence=equivalence, real_cache_and_initial_anchors=anchors, matrix=schedule('full'), power=power, result='PASS')
(OUT / 'preflight.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print('Preflight PASS; AC=', power['ac_line_status'], flush=True)
