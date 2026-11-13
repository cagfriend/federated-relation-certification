"""Balanced-Softmax private CE on clients 0 and 3; inference uses raw logits."""
import numpy as np

from experiments.private_workload.sampling import private_workload_epoch as original_epoch
from experiments.public_scaling.head import ce_loss_grad

CLIENTS = (0, 3)


def log_prior(labels, classes):
    counts = np.bincount(labels, minlength=classes)
    if len(counts) != classes or np.any(counts == 0):
        raise ValueError("Registered correction requires every pseudo cluster nonempty")
    return np.log(counts / counts.sum())


def private_workload_epoch(head, features, labels, config, seed, client, round_number, limit):
    if client not in CLIENTS:
        return original_epoch(head, features, labels, config, seed, client, round_number, limit)
    if limit is not None or config.private_epochs != 1 or len(labels) > config.private_batch:
        raise ValueError("Registered small-client update requires one full private batch")
    # The temporary bias only affects CE. Apply the gradient to the original head.
    # Cache 10 constants on this head, away from all teacher/public/test forwards.
    if not hasattr(head, "private_log_prior"):
        head.private_log_prior = log_prior(labels, config.classes)
    rng = np.random.default_rng(np.random.SeedSequence([seed, 401, client, round_number, 0]))
    ids = rng.permutation(len(labels))
    loss, dw, db = ce_loss_grad(features[ids], labels[ids], head.w, head.b + head.private_log_prior)
    head.apply(dw, db, config.head_lr)
    return loss, len(labels), np.arange(len(labels), dtype=np.int64)
