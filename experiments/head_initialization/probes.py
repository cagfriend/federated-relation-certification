"""Read-only diagnostics for native linear-head predictions."""

import numpy as np


def distribution(features, w, b, k, labels=None):
    """Summarize hard clusters and softmax confidence for a linear head."""
    x = np.asarray(features, dtype=np.float64)
    weight = np.asarray(w, dtype=np.float64)
    bias = np.asarray(b, dtype=np.float64)
    if x.ndim != 2 or weight.shape != (int(k), x.shape[1]) or bias.shape != (int(k),):
        raise ValueError('incompatible feature, head, or class dimensions')
    if x.shape[0] == 0 or not np.isfinite(x).all() or not np.isfinite(weight).all() or not np.isfinite(bias).all():
        raise ValueError('features and head parameters must be nonempty and finite')
    logits = x @ weight.T + bias
    order = np.argsort(logits, axis=1)
    # Match NumPy's native argmax tie behavior used by the training/evaluation path.
    predicted = logits.argmax(axis=1)
    counts = np.bincount(predicted, minlength=int(k))
    shifted = logits - logits.max(axis=1, keepdims=True)
    exp = np.exp(shifted)
    probs = exp / exp.sum(axis=1, keepdims=True)
    psort = np.sort(probs, axis=1)
    entropy = -(probs * np.log(np.maximum(probs, np.finfo(float).tiny))).sum(axis=1)
    result = dict(
        counts=counts.astype(int).tolist(), occupied=int(np.count_nonzero(counts)),
        empty=int(k - np.count_nonzero(counts)), largest=float(counts.max() / len(x)),
        sample_count=int(len(x)), softmax_mean=probs.mean(axis=0).tolist(),
        maxprob_mean=float(probs.max(axis=1).mean()), entropy_mean=float(entropy.mean()),
        top1_top2_logit_margin_mean=float(np.mean(logits[np.arange(len(x)), order[:, -1]] - logits[np.arange(len(x)), order[:, -2]])),
        top1_top2_prob_margin_mean=float(np.mean(psort[:, -1] - psort[:, -2])),
    )
    if labels is not None:
        target = np.asarray(labels)
        if target.shape != predicted.shape:
            raise ValueError('probe labels and predictions have different lengths')
        result['privatepseudo_fit'] = float(np.mean(predicted == target))
    return result
