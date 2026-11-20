"""Capture the new-seed teacher trajectories from the frozen STL-10 protocol."""

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch

from experiments.external_pilot.common import Wire, model_digest
from experiments.external_pilot.evaluate import scores
from experiments.external_pilot.prepare import load, prepare
from experiments.private_corrected_guard.run import digest
from experiments.public_scaling.certification import hard_relations, make_matching
from experiments.snapshot_certification_timing.design import checkpoints, require, seal
from experiments.snapshot_certification_timing.engine import Engine
from experiments.snapshot_external_comparison.selection import select_models
from experiments.snapshot_graph_scaling.design import cell_id
from experiments.snapshot_graph_scaling.inputs import choose_bank, load_bank, raw_sha


def capture_seed(out, cfg, cases, data, raw_data, identity, pending):
    cache = out/'cache'
    cache.mkdir(exist_ok=True)
    seed_dir = cache/str(cfg['seed'])
    if not seed_dir.exists():
        # Publish complete preparation as one directory, so a partial AE run can be retried.
        with TemporaryDirectory(dir=cache) as tmp:
            staged = Path(tmp)/'prepared'
            prepare(staged, data, cfg)
            staged.rename(seed_dir)
    partitions = {c['partition'] for c in cases}
    bank = None
    binary = data/'unlabeled_X.bin' if raw_data else None
    for part in sorted(partitions):
        cells = [c for c in cases if c['partition'] == part and cell_id(c) in pending]
        if not cells:
            continue
        models, train, meta = load(seed_dir, part, cfg)
        evaluation = torch.load(seed_dir/part/'evaluation.pt', weights_only=True)
        selected, selection = select_models(cfg, models, train)
        blocked = [r['client'] for r in selection if r['selected'] is None]
        record = dict(manifest=identity, partition=part, selection=selection,
                      initial_model_digest=meta['initial_model_digest'], input_files=meta['files'],
                      selected_model_digest=model_digest(selected), blocked_clients=blocked)
        if not blocked and bank is None:
            bank = choose_bank(out, cfg['seed'], train, max(c['public_size'] for c in cases),
                               binary, raw_data.get('unlabeled_X.bin'))
        for case in cells:
            cell = cell_id(case)
            print(f'Capturing {cell}', flush=True)
            path = out/'traces'/f'{cell}.npz'
            path.parent.mkdir(exist_ok=True)
            info = dict(record, case=case)
            if blocked:
                seal(path.with_suffix('.json'), dict(info, status='initialization_blocked'))
                continue
            public, ids = load_bank(out, case, train, bank)
            details = capture_trace(path, case, cfg, selected, train, evaluation, selection, public, ids)
            seal(path.with_suffix('.json'), dict(info, status='captured', **details))


def capture_trace(path, case, base, models, train, evaluation, selection, public, ids):
    cfg = dict(base, public_size=case['public_size'])
    torch.manual_seed(cfg['seed'])
    np.random.seed(cfg['seed'])
    initial_model = model_digest(models)
    algo = Engine(models, cfg, Wire(), train['private'], public.clone(), method='B', initialization='centers',
                  strength=.5, until=cfg['rounds'], all_clients=True)
    head_start = algo.state_digest()
    for pseudo, centers, selected in zip(algo.pseudo, algo.centers, selection, strict=True):
        expected = selected['candidates'][selected['selected']]
        require(digest(pseudo) == expected['pseudo_digest'] and digest(centers) == expected['centers_digest'],
                'Snapshot screening clusters differ from the training initialization')
    require(np.array_equal(algo.edges, make_matching(len(public), cfg['seed'])), 'Matching graph changed')
    with torch.no_grad():
        test_features = [model.encode(evaluation['test']).double().numpy() for model in models]
    truth = evaluation['truth'].numpy()
    # Native head is evaluated without another k-means fit or any training input from test labels.
    quality, same_edges, traffic, head_hashes = [], [], [], []
    packed, heads = [], [[] for _ in algo.heads]
    ticks = set(checkpoints(cfg))

    def evaluate(round_id):
        clients = [dict(client=i, **scores(truth, (x@head.w.T+head.b).argmax(1), cfg['classes']))
                   for i, (x, head) in enumerate(zip(test_features, algo.heads, strict=True))]
        quality.append(dict(round=round_id, clients=clients))

    evaluate(0)
    for rnd in range(1, cfg['rounds']+1):
        stat = algo.round(train['private'], public, cfg['seed'], rnd)
        snapshot, relations = algo.last_snapshot, algo.last_relations
        edge_count = min(len(algo.edges), cfg['public_steps']*cfg['relation_batch'])
        require(all(len(order) == edge_count for order in stat['public_orders']), 'Training budget changed')
        counts = np.sum(relations, axis=0)
        require(np.array_equal(counts, algo.protocol.counts), f'Round {rnd}: wrong aggregate')
        for c, (x, head, rel, target) in enumerate(zip(algo.public, snapshot, relations, stat['consumed'], strict=True)):
            w, b = head
            expected = hard_relations((x@w.T+b).argmax(1), algo.edges)
            require(np.array_equal(expected, rel) and np.array_equal(counts/len(algo.heads), target),
                    f'Round {rnd}, client {c}: wrong relation or student target')
            require(np.isfinite(w).all() and np.isfinite(b).all(), 'Non-finite teacher parameters')
            heads[c].append(head)
        packed.append([np.packbits(rel) for rel in relations])
        same_edges.append([float(r.mean()) for r in relations])
        traffic.append(algo.traffic())
        head_hashes.append(algo.state_digest())
        if rnd in ticks:
            evaluate(rnd)
    require(model_digest(models) == initial_model, 'Encoder changed during head training')
    arrays = {f'x{i}': x for i, x in enumerate(algo.public)}
    for i, snapshots in enumerate(heads):
        arrays[f'w{i}'] = np.stack([w for w, _ in snapshots])
        arrays[f'b{i}'] = np.stack([b for _, b in snapshots])
    temp = path.with_suffix('.npz.part')
    with temp.open('wb') as f:
        np.savez(f, edges=algo.edges, relations=np.asarray(packed), **arrays)
    temp.replace(path)
    return dict(payload_sha256=raw_sha(path), cfg=cfg, quality=quality, same_edges=same_edges, traffic=traffic,
                initial_head_digest=head_start, head_digests=head_hashes,
                graph_digest=digest(algo.edges), public_ids_digest=digest(ids.numpy()),
                comparisons=len(algo.edges)*len(algo.heads)*cfg['rounds'])
