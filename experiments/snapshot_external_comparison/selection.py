"""Reproduce the published terminal check and local snapshot rollback."""
import copy
from time import perf_counter
import warnings

import numpy as np
import torch
from sklearn.cluster import KMeans
from sklearn.exceptions import ConvergenceWarning
from torch import nn
from torch.nn import functional as F

from experiments.external_pilot.common import SSLModel, batches, model_digest
from experiments.private_corrected_guard.run import digest


@torch.no_grad()
def screen(cfg, client, model, private, public):
    k = cfg['classes']
    x = model.encode(private).double().numpy()
    z = model.encode(public).double().numpy()
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', category=ConvergenceWarning, message='Number of distinct clusters')
        km = KMeans(k, n_init=3, max_iter=100, random_state=cfg['seed'] + 101 * client).fit(x)
    centers = km.cluster_centers_
    labels = (z @ (2 * centers).T - np.sum(centers ** 2, axis=1)).argmax(axis=1)
    support = np.bincount(km.labels_, minlength=k)
    counts = np.bincount(labels, minlength=k)
    return dict(eligible=bool(np.all(support > 0)), private_support=support.tolist(),
                public_counts=counts.tolist(), private_largest=float(support.max() / len(x)),
                public_largest=float(counts.max() / len(z)), pair_count=int(counts @ (counts - 1)),
                pseudo_digest=digest(km.labels_), centers_digest=digest(centers))


def schedule(cfg, client, size):
    return [ix for epoch in range(cfg['ae_epochs'])
            for ix in batches(size, cfg['local_batch'], cfg['seed'] + 101 * client + epoch)]


def replay(cfg, client, private, cached, order):
    torch.manual_seed(cfg['seed'] + 220 + client)
    width = cfg['widths'][client]
    model = SSLModel(width)
    decoder = nn.Linear(width, private.shape[1])
    opt = torch.optim.Adam(list(model.encoder.parameters()) + list(decoder.parameters()), lr=cfg['ae_lr'])
    earlier = {}
    for step, ix in enumerate(order, 1):
        x = private[ix]
        opt.zero_grad()
        reconstruction = torch.sigmoid(decoder(F.relu(model.encoder.linear(x))))
        F.mse_loss(reconstruction, x).backward()
        opt.step()
        if step != len(order):
            earlier[step] = copy.deepcopy(model)
    if model_digest([model]) != model_digest([cached]):
        raise ValueError(f'Warm-up replay mismatch for client {client}')
    return earlier


def select_models(cfg, models, train):
    limit = .50
    chosen = models.copy()
    records = []
    for c, model in enumerate(models):
        start = perf_counter()
        x, z = train['private'][c], train['public']
        order = schedule(cfg, c, len(x))
        terminal = len(order)
        states = {terminal: model}
        probes = {terminal: screen(cfg, c, model, x, z)}

        def acceptable(probe):
            return probe['eligible'] and max(probe['private_largest'], probe['public_largest']) <= limit

        triggered = not acceptable(probes[terminal])
        selected = terminal
        if triggered:
            states.update(replay(cfg, c, x, model, order))
            probes.update({s: screen(cfg, c, state, x, z) for s, state in states.items() if s != terminal})
            eligible = [s for s, p in probes.items() if p['eligible']]
            within = [s for s in eligible if acceptable(probes[s])]
            selected = min(within or eligible, key=lambda s: (probes[s]['pair_count'], -s), default=None)
        if selected is not None:
            chosen[c] = states[selected]
        records.append(dict(client=c, terminal=terminal, selected=selected, candidates=probes, triggered=triggered,
                            still_concentrated=selected is not None and not acceptable(probes[selected]),
                            elapsed_seconds=perf_counter() - start))
    return chosen, records
