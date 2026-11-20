import os
import platform
import sys

import numpy as np
import sklearn
import torch
from threadpoolctl import threadpool_info

from experiments.external_pilot.prepare import read, sha, write
from experiments.external_pilot.run import ROOT, sources
from experiments.snapshot_external_comparison.run import FORMAL, ON, cfg_for, name

PLAN = ROOT/'docs/E38_CERTIFICATION_TIMING_PLAN.md'
TRIPLES = [('BED', 'EDB', 'DBE'), ('DEB', 'BDE', 'EBD')]
LEGACY_ROUND = ('round', 'head_digest', 'teacher_positive_rates', 'aggregate_positive_rate', 'traffic_delta')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def schedule(preset):
    contexts = FORMAL if preset == 'full' else FORMAL[:1]
    for stage in ('audit', 'timing'):
        for i, (seed, part) in enumerate(contexts):
            orders = ('BED',) if stage == 'audit' or preset == 'smoke' else TRIPLES[i % 2]
            for repeat, order in enumerate(orders, 1):
                for method in order:
                    yield dict(stage=stage, seed=seed, partition=part, repeat=repeat, method=method)


def case_id(case):
    return f"{case['seed']}_{case['partition']}"


def path_for(out, case):
    return out/case['stage']/name(case)


def receipt(path):
    return path.with_suffix('.sha256.json')


def seal(path, payload):
    write(path, payload)
    write(receipt(path), dict(sha256=sha(path)))


def sealed(path):
    require(path.is_file() and receipt(path).is_file() and read(receipt(path))['sha256'] == sha(path),
            f'Missing or invalid SHA-256 receipt: {path}')
    return read(path)


def history_pair(history, cfg, part):
    manifest = read(history/'manifest.json')
    done = read(history/'completed.json')
    seed = cfg['seed']
    require(manifest['configs'][str(seed)] == cfg, 'E38 config changed')
    paths, data = [], []
    for repeat in (1, 2):
        case = dict(seed=seed, partition=part, method=ON, repeat=repeat)
        path = history/'runs'/name(case)
        r = sealed(path)
        source_hash = manifest.get('original_manifest_sha256') or sha(history/'manifest.json')
        require(r['case'] == case and r['cfg'] == cfg and r['status'] == 'completed'
                and r['manifest_sha256'] == source_hash and done['runs'][path.name] == sha(path),
                f'E38 run identity mismatch: {path}')
        require([x['round'] for x in r['rows']] == list(range(1, cfg['rounds']+1))
                and [x['round'] for x in r['evaluations']] == checkpoints(cfg), 'E38 records incomplete')
        require(r['relation_audits'] == cfg['rounds'] * len(cfg['widths']) * (cfg['public_size']//2),
                'E38 relation audit count mismatch')
        paths.append(path)
        data.append(r)
    a, b = data
    require(all(a[k] == b[k] for k in ('initial_model_digest', 'selected_model_digest', 'initial_head_sources',
                                      'input_files', 'traffic')) and selection_core(a['selection']) == selection_core(b['selection'])
            and [legacy_round(x) for x in a['rows']] == [legacy_round(x) for x in b['rows']]
            and [legacy_eval(x) for x in a['evaluations']] == [legacy_eval(x) for x in b['evaluations']],
            'E38 technical replicates disagree')
    return a, {p.name: sha(p) for p in paths}


def checkpoints(cfg):
    return [0] + [i for i in range(1, cfg['rounds']+1) if i % cfg['eval_every'] == 0 or i == cfg['rounds']]


def selection_core(records):
    return [{k: v for k, v in r.items() if k != 'elapsed_seconds'} for r in records]


def legacy_round(row):
    return {k: row[k] for k in LEGACY_ROUND}


def legacy_eval(row):
    return {k: row[k] for k in ('round', 'clients', 'mean', 'cumulative_bytes')}


def environment():
    pools = sorted(({k: p.get(k) for k in ('internal_api', 'version', 'architecture', 'num_threads', 'prefix')}
                    for p in threadpool_info()), key=repr)
    return dict(python=sys.version, numpy=np.__version__, torch=str(torch.__version__),
                sklearn=sklearn.__version__, platform=platform.platform(), machine=platform.node(),
                logical_cpus=os.cpu_count(), torch_threads=torch.get_num_threads(),
                torch_interop_threads=torch.get_num_interop_threads(), threadpools=pools)
