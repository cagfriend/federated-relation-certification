"""Reproducible per-round private subsampling for the workload experiment.

The subset for (seed, client, round) is drawn from its own SeedSequence
stream (403), which no other part of the frozen core uses: private SGD
shuffling is 401, public shuffling is 402, head initialisation is 310.
The draw depends only on seed/client/round and the client's private
count, never on the method, so B/E/D consume identical private inputs
in every round. A fresh subset is drawn each round; over many rounds a
client still covers its whole private set, only the per-round workload
is capped.

When the cap is None (or reaches the client's full count) the original
``private_epoch`` runs on the untouched arrays, so the full-workload
case reproduces the frozen core bit for bit.
"""
import hashlib

import numpy as np

from experiments.public_scaling.head import private_epoch

STREAM = 403


def subset_indices(seed, client, round_number, count, limit):
    if limit is None or limit >= count:
        return np.arange(count)
    rng = np.random.default_rng(np.random.SeedSequence([seed, STREAM, client, round_number]))
    return rng.permutation(count)[:limit]


def subset_digest(indices_per_client):
    h = hashlib.sha256()
    for indices in indices_per_client:
        h.update(np.asarray(indices).astype('<u8').tobytes())
    return h.hexdigest()


def private_workload_epoch(head, features, labels, config, seed, client, round_number, limit):
    """One private epoch capped at ``limit`` samples; returns loss, endpoints, indices."""
    indices = subset_indices(seed, client, round_number, len(features), limit)
    if len(indices) == len(features):
        loss, endpoints = private_epoch(head, features, labels, config, seed, client, round_number)
    else:
        loss, endpoints = private_epoch(head, features[indices], labels[indices],
                                        config, seed, client, round_number)
    return loss, endpoints, indices
