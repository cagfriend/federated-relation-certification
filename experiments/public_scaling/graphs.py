"""Nested simple regular graphs using a complete-graph one-factorization."""
import numpy as np


def make_graph(samples, degree, seed):
    if samples < 2 or samples % 2 or not 1 <= degree < samples:
        raise ValueError('Need even sample count and 1 <= degree < samples')
    # Relabel round zero to adjacent pairs, invariant under public-prefix expansion.
    labels = np.empty(samples, dtype=np.uint32)
    labels[-1], labels[0] = 0, 1
    for j in range(1, samples // 2):
        labels[j], labels[samples - 1 - j] = 2 * j, 2 * j + 1
    rng = np.random.default_rng(np.random.SeedSequence([seed, 510]))
    shifts = np.concatenate(([0], rng.permutation(np.arange(1, samples - 1))))[:degree]
    layers = []
    for shift in shifts:
        ring = np.roll(np.arange(samples - 1), int(shift))
        left = np.concatenate(([samples - 1], ring[1:samples // 2]))
        right = np.concatenate(([ring[0]], ring[:samples // 2 - 1:-1]))
        layers.append(labels[np.column_stack((left, right))])
    edges = np.concatenate(layers)
    edges.sort(axis=1)
    edges = edges[np.lexsort((edges[:, 1], edges[:, 0]))]
    if (len(edges) != samples * degree // 2 or np.any(edges[:, 0] == edges[:, 1])
            or len(np.unique(edges, axis=0)) != len(edges)
            or not np.all(np.bincount(edges.ravel(), minlength=samples) == degree)):
        raise AssertionError('Graph construction invariant failed')
    return edges.astype(np.uint32, copy=False)
