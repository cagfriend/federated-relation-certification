"""Deterministic, read-only diagnostic probe selection and summaries."""
import hashlib

import numpy as np

PROBE_STREAM = 7901


def selection(seed, samples, size):
    """Choose sorted local public-pool positions from an isolated RNG stream."""
    if type(samples) is not int or samples < 1:
        raise ValueError('samples must be a positive integer')
    if type(size) is not int or size < 1 or size > samples:
        raise ValueError('probe size must be in [1, samples]')
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), PROBE_STREAM]))
    return np.sort(rng.choice(samples, size=size, replace=False)).astype(np.int64)


def _digest(array, dtype):
    return hashlib.sha256(np.asarray(array, dtype=dtype).tobytes()).hexdigest()


def manifest(seed, public_ids, size):
    """Describe the exact selected local positions and corresponding source IDs."""
    ids = np.asarray(public_ids)
    if ids.ndim != 1 or ids.dtype.kind not in 'iu':
        raise ValueError('public_ids must be a one-dimensional integer array')
    indices = selection(int(seed), len(ids), int(size))
    actual = ids[indices]
    return dict(seed=int(seed), stream=PROBE_STREAM, pool_size=int(len(ids)),
                probe_size=int(size), local_indices=indices.tolist(),
                local_indices_sha256=_digest(indices, '<i8'),
                public_ids=actual.astype(np.int64).tolist(),
                public_ids_sha256=_digest(actual, '<i8'))


def prediction_summary(features, head, labels=None):
    """Read-only predicted class histogram and optional agreement with labels."""
    from experiments.public_scaling.head import probabilities

    scores = probabilities(features, head.w, head.b)
    predicted = scores.argmax(axis=1)
    counts = np.bincount(predicted, minlength=head.b.size).astype(np.int64)
    result = dict(counts=counts.tolist(), occupied_clusters=int(np.count_nonzero(counts)),
                  largest_cluster_fraction=float(counts.max() / len(predicted)),
                  sample_count=int(len(predicted)))
    if labels is not None:
        target = np.asarray(labels)
        if target.shape != predicted.shape:
            raise ValueError('probe labels and predictions have different lengths')
        result['fixed_pseudo_fit'] = float(np.mean(predicted == target))
    return result


def head_distance(before, after):
    """Actual parameter displacement between two head snapshots."""
    dw = np.asarray(after.w) - np.asarray(before.w)
    db = np.asarray(after.b) - np.asarray(before.b)
    return dict(weight_l2=float(np.linalg.norm(dw)), bias_l2=float(np.linalg.norm(db)),
                parameter_l2=float(np.sqrt(np.sum(dw * dw) + np.sum(db * db))))
