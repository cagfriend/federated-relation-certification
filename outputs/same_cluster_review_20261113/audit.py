"""Audit E26–E29 and isolate low-capacity private head updates on cached features."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from threadpoolctl import threadpool_limits

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
sys.path.insert(0, str(ROOT))
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.head import Head, ce_loss_grad, private_epoch
from experiments.public_scaling.engine import evaluate


def read(path):
    return json.loads(path.read_bytes())


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(private, public, pseudo, edges, weights, bias, indices):
    def predict(x):
        return np.argmax(x @ weights.T + bias, axis=1)
    scores = private @ weights.T + bias
    prob = np.exp(scores - scores.max(axis=1, keepdims=True))
    prob /= prob.sum(axis=1, keepdims=True)
    labels = np.concatenate([predict(public[i:i + 1024]) for i in range(0, len(public), 1024)])
    counts = np.bincount(labels, minlength=len(weights))
    return dict(private_fit=float(np.mean(predict(private) == pseudo)),
                private_median_confidence=float(np.median(prob.max(axis=1))),
                public_occupied=int(np.count_nonzero(counts)), public_max=float(counts.max()/len(labels)),
                public_probe_counts=np.bincount(labels[indices], minlength=len(weights)).tolist(),
                same_edge=float(np.mean(labels[edges[:, 0]] == labels[edges[:, 1]])))


class FrequencyAdjustedPrivateHead(Head):
    """Expose shifted logits to the existing private CE for its single full batch."""
    def __init__(self, width, classes, seed, client, counts):
        super().__init__(width, classes, seed, client)
        self.log_prior = np.log(counts / counts.sum())

    def private_step(self, features, labels, cfg, seed, client, rr):
        # Use the same sample order and CE code; apply the update to the raw head.
        rng = np.random.default_rng(np.random.SeedSequence([seed, 401, client, rr, 0]))
        ids = rng.permutation(len(features))
        _, dw, db = ce_loss_grad(features[ids], labels[ids], self.w, self.b + self.log_prior)
        self.apply(dw, db, cfg.head_lr)


def audit(path):
    j = read(path)
    seed, part = j['seed'], j['partition']
    runs = ROOT / 'experiments'
    cfg = j['config']
    edges = make_graph(cfg['samples'], cfg['degree'], seed)
    assert hashlib.sha256(edges.astype('<u4').tobytes()).hexdigest() == j['graph_sha256']
    cache = Path(j['prepared_directory'])
    manifest = read(cache / 'prepared.json')
    assert (manifest['seed'], manifest['partition'], manifest['profile']) == (seed, part, 'strong')
    assert file_hash(cache/'test_labels.npy') == manifest['files']['test_labels.npy']
    test_labels = np.load(cache/'test_labels.npy', allow_pickle=False)
    initial = j['initial_diagnostics']['clients']
    indices = j['probe_manifest']['local_indices']
    diag = j['diagnostic_records']
    assert [r['round'] for r in diag] == [r['round'] for r in j['round_records']] == list(range(1,201))
    history = []
    for r, d in zip(j['round_records'], diag):
        rates = [c['positive_relation_fraction_T1'] for c in d['clients']]
        assert np.isclose(np.mean(rates), r['positive_relation_fraction'], atol=1e-12, rtol=0)
        history.append(dict(round=r['round'], rates=rates, mean=r['positive_relation_fraction']))
    profiles = {}
    for profile in ['equal', 'moderate', 'strong']:
        other = read(runs / 'quantity_heterogeneity' / 'results_full' / 'runs' / f'{part}_{profile}_seed{seed}_B.json')
        profiles[profile] = other['round_records'][-1]['positive_relation_fraction']
    branches = {}
    private_anchor = {}
    for name in ['baseline','private_only','low_lr']:
        other = read(runs / 'low_capacity_diagnostic' / 'results_full' / 'runs' / f'strong_{part}_seed{seed}_{name}.json')
        assert (other['graph_sha256'], other['initial_head_digest']) == (j['graph_sha256'], j['initial_head_digest'])
        last = other['diagnostic_records'][-1]
        branches[name] = dict(round=last['round'], small_rates=[last['clients'][c]['positive_relation_fraction_T1'] for c in [0,3]])
        if name == 'private_only':
            private_anchor = {d['round']: d for d in other['diagnostic_records']}
            private_test_anchor = other['metrics'][-1]['clients']
    clients = {}
    for client in [0,3]:
        def load_file(suffix):
            name = f'client_{client}_{suffix}.npy'
            assert file_hash(cache / name) == manifest['files'][name]
            return np.load(cache / name, mmap_mode='r', allow_pickle=False)
        private, public = load_file('private'), load_file('public')[:cfg['samples']]
        pseudo, centers = load_file('pseudo'), np.asarray(load_file('centers'), dtype=np.float64)
        assert np.bincount(pseudo, minlength=cfg['classes']).tolist() == initial[client]['fixed_pseudo_histogram']
        random = Head(private.shape[1], cfg['classes'], seed, client)
        raw = snapshot(private, public, pseudo, edges, random.w, random.b, indices)
        assert raw['public_probe_counts'] == initial[client]['public_probe_prediction']['counts']
        centroid = snapshot(private, public, pseudo, edges, 2*centers, -np.sum(centers**2, axis=1), indices)
        replay = {}
        counts = np.bincount(pseudo, minlength=cfg['classes'])
        assert np.all(counts > 0) and cfg['private_epochs'] == 1 and len(pseudo) <= cfg['private_batch']
        settings = SimpleNamespace(**cfg)
        evaluation_data = SimpleNamespace(test_labels=test_labels, test=[load_file('test')])
        evaluation_settings = SimpleNamespace(classes=cfg['classes'], dimensions=[private.shape[1]])
        for init in ['random', 'centroid', 'random_prior', 'centroid_prior']:
            head_args = (private.shape[1], cfg['classes'], seed, client)
            head = FrequencyAdjustedPrivateHead(*head_args, counts) if init.endswith('_prior') else Head(*head_args)
            if init.startswith('centroid'):
                head.w = 2*centers
                head.b = -np.sum(centers**2, axis=1)
            checkpoints = {}
            for rr in range(1, 201):
                if init.endswith('_prior'):
                    head.private_step(private, pseudo, settings, seed, client, rr)
                else:
                    private_epoch(head, private, pseudo, settings, seed, client, rr)
                if rr in [1, 20, 40, 160, 180, 200]:
                    s = snapshot(private, public, pseudo, edges, head.w, head.b, indices)
                    checkpoints[rr] = dict(same_edge=s['same_edge'], private_fit=s['private_fit'])
                    if init == 'random':
                        observed = private_anchor[rr]['clients'][client]
                        assert s['same_edge'] == observed['positive_relation_fraction_T1']
                        assert s['private_fit'] == observed['T1']['private']['fixed_pseudo_fit']
            test = evaluate([head], evaluation_data, evaluation_settings)['clients'][0]
            if init == 'random':
                assert test['cluster_counts'] == private_test_anchor[client]['cluster_counts']
                assert test['acc'] == private_test_anchor[client]['acc']
            checkpoints[200]['test'] = {k: test[k] for k in ('acc','nmi','ari','largest_cluster_fraction')}
            replay[init] = checkpoints
        probe_stage = {}
        for start,end in [(1,40),(161,200)]:
            values = [[d['clients'][client][stage]['public']['largest_cluster_fraction']
                       for stage in ['T0','T1','T2']] for d in diag[start-1:end]]
            probe_stage[f'{start}-{end}'] = np.diff(values, axis=1).mean(axis=0).tolist()
        clients[client] = dict(random=raw,centroid=centroid, private_only_replay=replay,
                               pseudo_counts=initial[client]['fixed_pseudo_histogram'],
                               private_fit_r200=diag[-1]['clients'][client]['T2']['private']['fixed_pseudo_fit'],
                               test_max_r200=j['metrics'][-1]['clients'][client]['largest_cluster_fraction'],
                               stage_mean_probe_max_changes=probe_stage)
    return dict(source=path.relative_to(ROOT).as_posix(), seed=seed, partition=part, historical_global_r200=profiles,
                matched_branches=branches, history=history, small_clients=clients)


if __name__ == '__main__':
    paths = sorted((ROOT/'experiments').glob('*local_public_lr*/results_full/runs/*_local_lr.json'))
    with threadpool_limits(limits=1):
        records = [audit(p) for p in paths]
    assert {(r['seed'], r['partition']) for r in records} == {(s,p) for s in [1001,1002] for p in ['iid','dirichlet_0.1']}
    (OUT / 'audit.json').write_text(json.dumps(records, indent=2, allow_nan=False) + '\n', encoding='utf-8')
