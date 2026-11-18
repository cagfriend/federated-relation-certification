"""Replay local autoencoder preparation one minibatch at a time."""

import argparse
import csv
import hashlib
import os
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault('LOKY_MAX_CPU_COUNT', '1')

import numpy as np
import torch
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits
from torch import nn
from torch.nn import functional as F

from experiments.external_pilot.common import SSLModel, batches, model_digest
from experiments.external_pilot.design import config
from experiments.external_pilot.evaluate import scores
from experiments.external_pilot.prepare import load, prepare, sha, write
from experiments.public_scaling.certification import hard_relations, make_matching


ROOT = Path(__file__).resolve().parents[2]


def geometry(features):
    """Centered spectrum plus absolute dispersion to distinguish concentration from collapse."""
    centered = features - features.mean(axis=0)
    spectrum = np.linalg.svd(centered, compute_uv=False) ** 2
    energy = float(spectrum.sum())
    shares = spectrum / energy if energy else spectrum
    return dict(pc1_share=float(shares[0]) if energy else None,
                effective_dim=float(1.0 / (shares @ shares)) if energy else None,
                centered_energy_per_example=energy / len(features))


@torch.no_grad()
def observe(model, private, public, edges, k, cluster_seed, evaluation):
    raw = F.relu(model.encoder.linear(public)).double().numpy()
    public_features = model.encode(public).double().numpy()
    private_features = model.encode(private).double().numpy()
    km = KMeans(n_clusters=k, n_init=3, max_iter=100, random_state=cluster_seed)
    km.fit(private_features)
    w = 2.0 * km.cluster_centers_
    b = -(km.cluster_centers_ ** 2).sum(axis=1)
    # Match the cluster head used to generate public hard relations.
    private_labels = (private_features @ w.T + b).argmax(axis=1)
    labels = (public_features @ w.T + b).argmax(axis=1)
    private_counts = np.bincount(private_labels, minlength=k)
    public_counts = np.bincount(labels, minlength=k)
    active = raw > 0
    active_rates = active.mean(axis=0)
    _, mask_counts = np.unique(np.packbits(active, axis=1), return_counts=True, axis=0)
    norm = np.linalg.norm(raw, axis=1)
    row = dict(
        raw=geometry(raw), normalized=geometry(public_features),
        raw_norm_quantiles=np.quantile(norm, [.1, .5, .9]).tolist(),
        normalized_mean_direction_norm=float(np.linalg.norm(public_features.mean(axis=0))),
        active_channels_mean=float(active.sum(axis=1).mean()),
        active_channels_quantiles=np.quantile(active.sum(axis=1), [.1, .5, .9]).tolist(),
        activation_rates_by_channel=active_rates.tolist(),
        channels_never_active=int(np.count_nonzero(active_rates == 0)),
        channels_always_active=int(np.count_nonzero(active_rates == 1)),
        most_common_activation_mask_share=float(mask_counts.max() / len(raw)),
        zero_public_features=int(np.count_nonzero(norm == 0)),
        private_cluster_counts=private_counts.tolist(),
        public_cluster_counts=public_counts.tolist(),
        private_largest=float(private_counts.max() / len(private_labels)),
        public_largest=float(public_counts.max() / len(labels)),
        private_occupied=int(np.count_nonzero(private_counts)),
        public_occupied=int(np.count_nonzero(public_counts)),
        public_same_cluster_rate=float(hard_relations(labels, edges).mean()),
        random_distinct_pair_same_cluster=float(
            (public_counts @ (public_counts - 1)) / (len(labels) * (len(labels) - 1))),
    )
    if evaluation is not None:
        test = model.encode(evaluation['test']).double().numpy()
        pred = (test @ w.T + b).argmax(axis=1)
        row['test'] = scores(evaluation['truth'].numpy(), pred, k)
    return row


def replay(client, cfg, private, public, cached, evaluation):
    init_seed = cfg['seed'] + 220 + client
    torch.manual_seed(init_seed)
    model = SSLModel(cfg['widths'][client])
    decoder = nn.Linear(cfg['widths'][client], private.shape[1])
    optimizer = torch.optim.Adam(list(model.encoder.parameters()) + list(decoder.parameters()),
                                 lr=cfg['ae_lr'])
    edges = make_matching(len(public), cfg['seed'])
    cluster_seed = cfg['seed'] + 101 * client

    def snapshot():
        return observe(model, private, public, edges, cfg['classes'], cluster_seed, evaluation)

    rows = [dict(step=0, epoch=None, batch=None, loss_before_update=None, **snapshot())]
    for epoch in range(cfg['ae_epochs']):
        for batch, indices in enumerate(batches(len(private), cfg['local_batch'],
                                                cfg['seed'] + 101 * client + epoch), start=1):
            x = private[indices]
            optimizer.zero_grad()
            predicted = torch.sigmoid(decoder(F.relu(model.encoder.linear(x))))
            loss = F.mse_loss(predicted, x)
            loss.backward()
            optimizer.step()
            rows.append(dict(step=len(rows), epoch=epoch + 1, batch=batch, batch_size=len(indices),
                             batch_order_sha256=hashlib.sha256(indices.astype('<i8').tobytes()).hexdigest(),
                             loss_before_update=float(loss.item()), **snapshot()))

    # Observers run between updates. Byte-identical cached parameters also test
    # whether the probe perturbed the historical warm-up trajectory.
    replay_digest, cached_digest = model_digest([model]), model_digest([cached])
    if replay_digest != cached_digest:
        raise ValueError(f'Client {client} replay differs from the cached warm-up. '
                         'Check the cache, code and original CPU/library environment.')
    return dict(client=client, width=cfg['widths'][client], private_samples=len(private),
                model_seed=init_seed, kmeans_seed=cluster_seed, cached_model_sha256=cached_digest,
                replay_model_sha256=replay_digest, snapshots=rows)


def write_reports(output, results):
    lines = ['# Encoder warm-up replay', '',
             'All reported replays exactly matched their cached final model.', '',
             '| Partition | Client | Step | PC1 raw | PC1 normalized | Effective dimension normalized |'
             ' Public largest cluster | Public same-cluster edges | Private occupied |',
             '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    table = []
    for result in results:
        for row in result['snapshots']:
            item = dict(partition=result['partition'], client=result['client'], step=row['step'],
                        raw_pc1=row['raw']['pc1_share'], normalized_pc1=row['normalized']['pc1_share'],
                        raw_effective_dim=row['raw']['effective_dim'],
                        normalized_effective_dim=row['normalized']['effective_dim'],
                        raw_centered_energy=row['raw']['centered_energy_per_example'],
                        normalized_centered_energy=row['normalized']['centered_energy_per_example'],
                        public_largest=row['public_largest'],
                        public_same_cluster_rate=row['public_same_cluster_rate'],
                        random_pair_rate=row['random_distinct_pair_same_cluster'],
                        private_largest=row['private_largest'], private_occupied=row['private_occupied'],
                        public_occupied=row['public_occupied'],
                        active_channels_mean=row['active_channels_mean'],
                        channels_always_active=row['channels_always_active'],
                        channels_never_active=row['channels_never_active'],
                        most_common_activation_mask_share=row['most_common_activation_mask_share'],
                        loss_before_update=row['loss_before_update'])
            if 'test' in row:
                item.update({f'test_{k}': row['test'][k] for k in ('largest', 'acc', 'nmi', 'ari')})
            table.append(item)
            raw_pc1 = 'NA' if item['raw_pc1'] is None else f"{item['raw_pc1']:.1%}"
            normalized_pc1 = 'NA' if item['normalized_pc1'] is None else f"{item['normalized_pc1']:.1%}"
            dim = item['normalized_effective_dim']
            dimension = 'NA' if dim is None else f'{dim:.2f}'
            lines.append(f"| {item['partition']} | {item['client']} | {item['step']} | {raw_pc1} |"
                         f" {normalized_pc1} | {dimension} | {item['public_largest']:.1%} |"
                         f" {item['public_same_cluster_rate']:.1%} | {item['private_occupied']} |")
    with (output / 'steps.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    (output / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def probe(cache, cfg, partitions, score_test):
    results, inputs = [], {}
    for partition in partitions:
        models, train, meta = load(cache, partition, cfg)
        inputs[partition] = dict(manifest_sha256=sha(cache / partition / 'manifest.json'),
                                 files=meta['files'])
        evaluation = (torch.load(cache / partition / 'evaluation.pt', weights_only=True)
                      if score_test else None)
        for client in (1, 4):
            result = replay(client, cfg, train['private'][client], train['public'], models[client], evaluation)
            results.append(dict(partition=partition, **result))
            print(f'{partition} client{client}: {len(result["snapshots"]) - 1} updates, exact cache match',
                  flush=True)
    return results, inputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preset', choices=('pilot', 'smoke'), default='pilot')
    parser.add_argument('--partition', nargs='+', default=['iid'], choices=('iid', 'dirichlet_0.1'))
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--score-test', action='store_true', help='Retrospective scoring only, never used for fitting.')
    args = parser.parse_args()
    cfg = config(args.preset)
    if len(set(args.partition)) != len(args.partition) or not set(args.partition).issubset(cfg['partitions']):
        parser.error('Use distinct partitions supported by the selected preset.')
    cache = args.cache
    if cache is None and args.preset == 'pilot':
        cache = ROOT / 'experiments/external_pilot/results_pilot_observed/cache'
    if cache is not None:
        cache = cache.resolve()
    output = (args.output or ROOT / f'experiments/encoder_collapse_probe/results_{args.preset}').resolve()
    if cache is not None and (output.is_relative_to(cache) or cache.is_relative_to(output)):
        parser.error('Output overlaps the input cache.')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('Output must be a new or empty directory.')

    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    with threadpool_limits(1):
        if cache is None:
            with TemporaryDirectory(prefix='encoder_probe_', dir=ROOT / 'experiments/encoder_collapse_probe') as tmp:
                prepare(Path(tmp), None, cfg)
                results, inputs = probe(Path(tmp), cfg, args.partition, args.score_test)
        else:
            results, inputs = probe(cache, cfg, args.partition, args.score_test)
    output.mkdir(parents=True, exist_ok=True)
    write_reports(output, results)
    write(output / 'results.json', dict(config=cfg, inputs=inputs, test_scoring=args.score_test,
                                       probe_sha256=sha(Path(__file__)), torch_version=str(torch.__version__),
                                       results=results))
    print(output / 'report.md')


if __name__ == '__main__':
    main()
