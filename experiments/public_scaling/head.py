"""Float64 linear heads; fresh student forwards with analytic backpropagation."""
import numpy as np
from scipy.special import logsumexp


def probabilities(x, w, b):
    scores = np.asarray(x, dtype=np.float64) @ w.T + b
    scores -= scores.max(axis=1, keepdims=True)
    p = np.exp(scores)
    return p / p.sum(axis=1, keepdims=True)


def ce_loss_grad(x, y, w, b):
    x = np.asarray(x, dtype=np.float64)
    scores = x @ w.T + b
    loss = float(np.mean(logsumexp(scores, axis=1) - scores[np.arange(len(y)), y]))
    p = probabilities(x, w, b)
    p[np.arange(len(y)), y] -= 1
    p /= len(y)
    return loss, p.T @ x, p.sum(axis=0)


def relation_loss_grad(x, edges, targets, w, b):
    """BCE on dot products of two softmax vectors, including both endpoints.

    x contains unique endpoints of this batch; edges indexes those rows. The
    clip derivative is zero outside (eps,1-eps), matching the clipped loss.
    """
    x = np.asarray(x, dtype=np.float64)
    p = probabilities(x, w, b)
    left, right = edges.T
    q = np.einsum("ij,ij->i", p[left], p[right])
    eps = 1e-12
    safe = np.clip(q, eps, 1 - eps)
    loss = -np.mean(targets * np.log(safe) + (1 - targets) * np.log1p(-safe))
    derivative = (safe - targets) / (safe * (1 - safe) * len(edges))
    derivative *= (q > eps) & (q < 1 - eps)
    grad_p = np.zeros_like(p)
    np.add.at(grad_p, left, derivative[:, None] * p[right])
    np.add.at(grad_p, right, derivative[:, None] * p[left])
    grad_scores = p * (grad_p - (grad_p * p).sum(axis=1, keepdims=True))
    return float(loss), grad_scores.T @ x, grad_scores.sum(axis=0)


class Head:
    def __init__(self, dimension, classes, seed, client):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 310, client]))
        self.w = rng.normal(size=(classes, dimension)) / np.sqrt(dimension)
        self.b = np.zeros(classes, dtype=np.float64)

    def apply(self, dw, db, rate):
        self.w -= rate * dw
        self.b -= rate * db
        if not np.isfinite(self.w).all() or not np.isfinite(self.b).all():
            raise ArithmeticError("Nonfinite head; no silent repair")


def private_epoch(head, features, labels, config, seed, client, round_number):
    weighted_loss, endpoints = 0.0, 0
    for epoch in range(config.private_epochs):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 401, client, round_number, epoch]))
        order = rng.permutation(len(features))
        for offset in range(0, len(order), config.private_batch):
            ids = order[offset:offset + config.private_batch]
            loss, dw, db = ce_loss_grad(features[ids], labels[ids], head.w, head.b)
            head.apply(dw, db, config.head_lr)
            weighted_loss += loss * len(ids)
            endpoints += len(ids)
    return weighted_loss / endpoints, endpoints


def public_epoch(head, features, edges, targets, config, seed, client, round_number):
    weighted_loss, edge_count, endpoints = 0.0, 0, 0
    for epoch in range(config.public_epochs):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 402, client, round_number, epoch]))
        order = rng.permutation(len(edges))
        for offset in range(0, len(order), config.public_edge_batch):
            ids = order[offset:offset + config.public_edge_batch]
            vertices, inverse = np.unique(edges[ids].ravel(), return_inverse=True)
            # Always a new student forward at the CURRENT head. No teacher
            # logits, gaps, predicted labels, or candidate cache is used here.
            loss, dw, db = relation_loss_grad(features[vertices], inverse.reshape(-1, 2),
                                              targets[ids], head.w, head.b)
            head.apply(dw, db, config.head_lr * config.public_weight)
            weighted_loss += loss * len(ids)
            edge_count += len(ids)
            endpoints += len(vertices)
    return weighted_loss / edge_count, endpoints
