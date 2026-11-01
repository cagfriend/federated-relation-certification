"""Read-only diagnostic probes for the STL-10 transfer experiment."""
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

from experiments.public_scaling.head import ce_loss_grad, relation_loss_grad


_BATCH = 512


def _head_arrays(head):
    """Return validated float64 views of a linear head without changing it."""
    w = np.asarray(head.w, dtype=np.float64)
    b = np.asarray(head.b, dtype=np.float64)
    if w.ndim != 2 or b.shape != (w.shape[0],):
        raise ValueError("head must expose w=(classes,features) and b=(classes,)")
    if not np.isfinite(w).all() or not np.isfinite(b).all():
        raise ValueError("head contains non-finite parameters")
    return w, b


def probe(head, z, pseudo=None, indices=None):
    """Summarize a linear head's predictions, optionally against pseudo labels."""
    w, b = _head_arrays(head)
    all_features = np.asarray(z)
    if all_features.ndim != 2 or all_features.shape[1] != w.shape[1]:
        raise ValueError("z must be a 2D matrix with the head feature width")
    if len(all_features) == 0:
        raise ValueError("z must contain at least one sample")
    if not np.isfinite(all_features).all():
        raise ValueError("z contains non-finite values")
    chosen = np.arange(len(all_features)) if indices is None else np.asarray(indices, dtype=np.int64)
    if chosen.ndim != 1 or len(chosen) == 0 or np.any((chosen < 0) | (chosen >= len(all_features))):
        raise ValueError("indices must be a nonempty valid index vector")
    features = all_features[chosen]
    counts = np.zeros(w.shape[0], dtype=np.int64)
    confidence_sum = 0.0
    selected_predictions = np.empty(len(features), dtype=np.int64) if pseudo is not None else None
    pseudo_labels = None if pseudo is None else np.asarray(pseudo)
    if pseudo_labels is not None:
        if pseudo_labels.shape != (len(all_features),) or not np.issubdtype(pseudo_labels.dtype, np.integer):
            raise ValueError("pseudo must be an integer vector aligned with z")
        if np.any((pseudo_labels < 0) | (pseudo_labels >= w.shape[0])):
            raise ValueError("pseudo labels fall outside the head classes")
        pseudo_labels = pseudo_labels[chosen]
    for start in range(0, len(features), _BATCH):
        stop = min(start + _BATCH, len(features))
        scores = np.asarray(features[start:stop], dtype=np.float64) @ w.T + b
        scores -= scores.max(axis=1, keepdims=True)
        exp_scores = np.exp(scores)
        probs = exp_scores / exp_scores.sum(axis=1, keepdims=True)
        pred = probs.argmax(axis=1)
        counts += np.bincount(pred, minlength=w.shape[0])
        confidence_sum += float(probs.max(axis=1).sum())
        if selected_predictions is not None:
            selected_predictions[start:stop] = pred
    result = {
        "cluster_counts": counts.tolist(),
        "occupied_clusters": int(np.count_nonzero(counts)),
        "largest_cluster_fraction": float(counts.max() / len(features)),
        "mean_confidence": float(confidence_sum / len(features)),
    }
    if pseudo_labels is not None:
        # Recompute only requested rows in bounded chunks for numerically stable CE.
        loss_sum = 0.0
        accuracy = 0
        for start in range(0, len(features), _BATCH):
            stop = min(start + _BATCH, len(features))
            scores = np.asarray(features[start:stop], dtype=np.float64) @ w.T + b
            maximum = scores.max(axis=1)
            logsum = maximum + np.log(np.exp(scores - maximum[:, None]).sum(axis=1))
            labels = pseudo_labels[start:stop]
            loss_sum += float((logsum - scores[np.arange(len(labels)), labels]).sum())
            accuracy += int(np.count_nonzero(selected_predictions[start:stop] == labels))
        result["pseudo_ce"] = float(loss_sum / len(features))
        result["pseudo_accuracy"] = float(accuracy / len(features))
    return result


def feature_probe(z):
    """Report finite-value, norm, and centered-spread statistics for features."""
    x = np.asarray(z, dtype=np.float64)
    if x.ndim != 2 or not len(x):
        raise ValueError("z must be a nonempty 2D feature matrix")
    finite_fraction = float(np.isfinite(x).sum() / x.size)
    if finite_fraction != 1.0:
        raise ValueError("z contains non-finite values")
    norms = np.linalg.norm(x, axis=1)
    mean = x.mean(axis=0)
    centered_rms = float(np.sqrt(np.mean(np.sum((x - mean) ** 2, axis=1))))
    mean_norm = float(np.linalg.norm(mean))
    return {
        "finite_fraction": finite_fraction,
        "norm_mean": float(norms.mean()),
        "norm_std": float(norms.std()),
        "norm_min": float(norms.min()),
        "norm_max": float(norms.max()),
        "centered_discrete_rms": centered_rms,
        "mean_norm": mean_norm,
        "spread_to_mean_scale": float(centered_rms / mean_norm) if mean_norm > 0 else None,
    }


def nearest_centers(z, centers):
    """Return nearest-center labels using float64 squared Euclidean distance."""
    x = np.asarray(z)
    c = np.asarray(centers)
    if x.ndim != 2 or c.ndim != 2 or x.shape[1] != c.shape[1] or not len(c):
        raise ValueError("z and centers must be 2D arrays with matching nonzero width")
    if not np.isfinite(x).all() or not np.isfinite(c).all():
        raise ValueError("z and centers must be finite")
    c64 = np.asarray(c, dtype=np.float64)
    c_norm = np.sum(c64 * c64, axis=1)
    labels = np.empty(len(x), dtype=np.int64)
    for start in range(0, len(x), _BATCH):
        block = np.asarray(x[start:start + _BATCH], dtype=np.float64)
        distances = np.sum(block * block, axis=1)[:, None] + c_norm[None, :] - 2.0 * (block @ c64.T)
        labels[start:start + len(block)] = distances.argmin(axis=1)
    return labels


def fixed_public_indices(cfg, seed, client):
    """Stable per-client public probe indices from independent stream 610."""
    population = int(cfg.samples)
    if population < 1:
        raise ValueError("cfg.samples must be positive")
    size = min(1024, population)
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), 610, int(client)]))
    return rng.permutation(population)[:size].astype(np.int64, copy=False)


def _center_test_scores(truth, predicted, classes):
    truth = np.asarray(truth, dtype=np.int64)
    contingency = np.zeros((int(truth.max()) + 1, classes), dtype=np.int64)
    np.add.at(contingency, (truth, predicted), 1)
    row, col = linear_sum_assignment(-contingency)
    return {
        "acc": float(contingency[row, col].sum() / len(truth)),
        "nmi": float(normalized_mutual_info_score(truth, predicted)),
        "ari": float(adjusted_rand_score(truth, predicted)),
    }


def initial_inspection(data, heads, cfg):
    """Read-only cache inspection: pseudo-labels, center assignments, and heads."""
    if not (len(heads) == len(data.private) == len(cfg.dimensions)):
        raise ValueError("heads and prepared client data must align with cfg.dimensions")
    clients = []
    for client, head in enumerate(heads):
        pseudo = np.asarray(data.pseudo[client], dtype=np.int64)
        private_z = data.private[client]
        centers_path = Path(data.directory) / f"client_{client}_centers.npy"
        centers = np.load(centers_path, allow_pickle=False)
        private_center = nearest_centers(private_z, centers)
        private_hist = np.bincount(pseudo, minlength=cfg.classes)
        rec = {
            "client": client,
            "private_pseudo_histogram": private_hist.astype(int).tolist(),
            "private_pseudo_nearest_center_mismatches": int(np.count_nonzero(private_center != pseudo)),
            "private_center_probe": _prediction_summary(private_center, cfg.classes),
            "private_features": feature_probe(private_z),
            "head_private": probe(head, private_z, pseudo),
        }
        for split in ("public", "test"):
            z = getattr(data, split)[client]
            center_pred = nearest_centers(z, centers)
            rec[f"{split}_center_probe"] = _prediction_summary(center_pred, cfg.classes)
            rec[f"{split}_head"] = probe(head, z)
            if split == "test" and hasattr(data, "test_labels"):
                rec["test_center_metrics"] = _center_test_scores(data.test_labels, center_pred, cfg.classes)
        clients.append(rec)
    return {"clients": clients}


def _prediction_summary(predicted, classes):
    counts = np.bincount(predicted, minlength=classes)
    return {
        "cluster_counts": counts.astype(int).tolist(),
        "occupied_clusters": int(np.count_nonzero(counts)),
        "largest_cluster_fraction": float(counts.max() / len(predicted)) if len(predicted) else 0.0,
    }


def _cosine(a, b):
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return None
    return float(np.dot(a, b) / (na * nb))


def gradient_probe(head, private_z, pseudo, public_z, edges, targets, cfg, seed, client):
    """Measure fixed-batch private/public gradients without applying updates."""
    w, b = _head_arrays(head)
    private_x = np.asarray(private_z)
    pseudo_arr = np.asarray(pseudo, dtype=np.int64)
    public_x = np.asarray(public_z)
    edge_arr = np.asarray(edges, dtype=np.int64)
    target_arr = np.asarray(targets, dtype=np.float64)
    if private_x.ndim != 2 or private_x.shape[1] != w.shape[1] or pseudo_arr.shape != (len(private_x),):
        raise ValueError("private features and pseudo labels have incompatible shapes")
    if public_x.ndim != 2 or public_x.shape[1] != w.shape[1]:
        raise ValueError("public features have an incompatible shape")
    if edge_arr.ndim != 2 or edge_arr.shape[1] != 2 or target_arr.shape != (len(edge_arr),):
        raise ValueError("edges and targets have incompatible shapes")
    if len(private_x) == 0 or len(edge_arr) == 0 or not np.isfinite(target_arr).all():
        raise ValueError("gradient probe requires nonempty finite data")
    if np.any((edge_arr < 0) | (edge_arr >= len(public_x))):
        raise ValueError("edge endpoint outside public feature matrix")
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), 611, int(client)]))
    pids = rng.permutation(len(private_x))[:min(128, len(private_x))]
    eids = rng.permutation(len(edge_arr))[:min(256, len(edge_arr))]
    loss_ce, ce_w, ce_b = ce_loss_grad(private_x[pids], pseudo_arr[pids], w, b)
    local_edges = edge_arr[eids]
    vertices, inverse = np.unique(local_edges.ravel(), return_inverse=True)
    loss_rel, rel_w, rel_b = relation_loss_grad(public_x[vertices], inverse.reshape(-1, 2),
                                                 target_arr[eids], w, b)
    ce = np.concatenate((ce_w.ravel(), ce_b.ravel()))
    rel = np.concatenate((rel_w.ravel(), rel_b.ravel()))
    lr = float(cfg.head_lr)
    public_scale = lr * float(cfg.public_weight)
    return {
        "private_sample_count": int(len(pids)),
        "public_edge_count": int(len(eids)),
        "private_ce_loss": float(loss_ce),
        "public_relation_loss": float(loss_rel),
        "private_gradient_norm": float(np.linalg.norm(ce)),
        "public_gradient_norm": float(np.linalg.norm(rel)),
        "gradient_cosine": _cosine(ce, rel),
        "private_update_norm": float(lr * np.linalg.norm(ce)),
        "public_weighted_update_norm": float(public_scale * np.linalg.norm(rel)),
    }
