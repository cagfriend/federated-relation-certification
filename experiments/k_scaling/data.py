"""K-scaling preparation that reuses the frozen STL-10 private features."""
from dataclasses import replace
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

import numpy as np
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits

from experiments.stl10_transfer import data as transfer_data


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _runtime_identity():
    return {name: importlib.metadata.version(name)
            for name in ("numpy", "scikit-learn", "scipy")}


def _identity():
    return {"data.py": _sha(Path(__file__)), "runtime": _runtime_identity()}


def _key(base_path, base_hash, cfg, seed, partition, fixture):
    value = {"base_directory": str(base_path.resolve()), "base_metadata_sha256": base_hash,
             "config": cfg.preparation(), "seed": int(seed), "partition": partition,
             "fixture": bool(fixture), "identity": _identity(), "format": 1}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:20]


def _paths(directory, clients):
    return [Path(directory) / f"client_{i}_pseudo.npy" for i in range(clients)]


def pseudo_paths(directory):
    directory = Path(directory)
    meta = json.loads((directory / "prepared_k.json").read_text(encoding="utf-8"))
    if meta["classes"] == 10:
        base = Path(meta["base_directory"])
        return [base / f"client_{i}_pseudo.npy" for i in range(len(meta["config"]["dimensions"]))]
    return _paths(directory, len(meta["config"]["dimensions"]))


def prepare(base_directory, spec, cache_root, *, fixture=False):
    spec.validate()
    cfg = spec.config
    if cfg.classes not in (10, 16, 32, 64):
        raise ValueError("K-scaling supports classes 10, 16, 32, or 64")
    base_directory = Path(base_directory).resolve()
    base_cfg = replace(cfg, classes=10)
    base_cfg.validate()
    base_marker = base_directory / "prepared.json"
    base_meta = json.loads(base_marker.read_text(encoding="utf-8"))
    seed = int(base_meta['seed'])
    partition = base_meta['partition']
    transfer_data.verify(base_directory, base_cfg, seed, partition, fixture=fixture)
    base_marker = base_directory / "prepared.json"
    base_hash = _sha(base_marker)
    base_meta = json.loads(base_marker.read_text(encoding="utf-8"))
    key = _key(base_directory, base_hash, cfg, seed, partition, fixture)
    directory = Path(cache_root) / f"k{cfg.classes}_seed{seed}_{partition}_{key}"
    marker = directory / "prepared_k.json"
    if marker.is_file():
        return verify(directory, base_directory, spec, fixture=fixture) and directory
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Refusing to reuse partial K-scaling cache: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    clients = len(cfg.dimensions)
    records = []
    source_manifest = {}
    started_all = time.perf_counter()
    for client in range(clients):
        pseudo_name = f"client_{client}_pseudo.npy"
        centers_name = f"client_{client}_centers.npy"
        if cfg.classes == 10:
            pseudo_path = base_directory / pseudo_name
            centers_path = base_directory / centers_name
            pseudo = np.load(pseudo_path, mmap_mode="r", allow_pickle=False)
            centers = np.load(centers_path, mmap_mode="r", allow_pickle=False)
            elapsed = 0.0
            n = len(pseudo)
        else:
            feature_path = base_directory / f"client_{client}_private.npy"
            features = np.load(feature_path, mmap_mode="r", allow_pickle=False)
            n = len(features)
            t0 = time.perf_counter()
            with threadpool_limits(limits=cfg.threads):
                km = KMeans(n_clusters=cfg.classes, n_init=cfg.kmeans_restarts,
                            max_iter=cfg.kmeans_max_iter, random_state=seed + client * 101)
                labels = km.fit_predict(features)
            elapsed = time.perf_counter() - t0
            pseudo_path = directory / pseudo_name
            centers_path = directory / centers_name
            np.save(pseudo_path, labels.astype(np.int64))
            np.save(centers_path, km.cluster_centers_)
            pseudo = labels
            centers = km.cluster_centers_
        source_manifest[pseudo_name] = _sha(pseudo_path)
        source_manifest[centers_name] = _sha(centers_path)
        records.append({"client": client, "n": int(n),
                        "pseudo_histogram": np.bincount(np.asarray(pseudo), minlength=cfg.classes).tolist(),
                        "incremental_kmeans_seconds": float(elapsed),
                        "pseudo_sha256": source_manifest[pseudo_name],
                        "centers_sha256": source_manifest[centers_name]})
    metadata = {"format": 1, "base_directory": str(base_directory),
                "base_prepared_sha256": base_hash, "config": cfg.preparation(),
                "seed": seed, "partition": partition, "fixture": bool(fixture),
                "source_identity": base_meta.get("preparation_identity"),
                "identity": _identity(), "classes": cfg.classes, "clients": records,
                "asset_hashes": source_manifest,
                "incremental_kmeans_seconds": time.perf_counter() - started_all if cfg.classes == 10 else sum(x["incremental_kmeans_seconds"] for x in records)}
    metadata["incremental_kmeans_seconds"] = 0.0 if cfg.classes == 10 else metadata["incremental_kmeans_seconds"]
    metadata['additional_kmeans_seconds'] = metadata['incremental_kmeans_seconds']
    metadata['additional_preparation_seconds'] = time.perf_counter() - started_all
    (directory / "prepared_k.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    verify(directory, base_directory, spec, fixture=fixture)
    return directory


def verify(directory, base_directory, spec, *, fixture=False):
    directory = Path(directory)
    cfg = spec.config
    base_directory = Path(base_directory).resolve()
    base_meta = json.loads((base_directory / 'prepared.json').read_text(encoding='utf-8'))
    seed = int(base_meta['seed'])
    partition = base_meta['partition']
    base_cfg = replace(cfg, classes=10)
    transfer_data.verify(base_directory, base_cfg, seed, partition, fixture=fixture)
    marker = directory / "prepared_k.json"
    meta = json.loads(marker.read_text(encoding="utf-8"))
    if (meta.get("base_directory") != str(base_directory) or
            meta.get("base_prepared_sha256") != _sha(base_directory / "prepared.json") or
            meta.get("config") != cfg.preparation() or meta.get("seed") != seed or
            meta.get("partition") != partition or meta.get("fixture") is not bool(fixture) or
            meta.get("identity") != _identity() or meta.get("source_identity") != json.loads((base_directory / "prepared.json").read_text(encoding="utf-8")).get("preparation_identity") or
            meta.get("classes") != cfg.classes):
        raise ValueError("K-scaling preparation identity mismatch")
    clients = len(cfg.dimensions)
    if len(meta.get("clients", [])) != clients:
        raise ValueError("K-scaling client count mismatch")
    for i, record in enumerate(meta["clients"]):
        pp = pseudo_paths(directory)[i]
        cp = (base_directory if cfg.classes == 10 else directory) / f"client_{i}_centers.npy"
        p = np.load(pp, mmap_mode="r", allow_pickle=False)
        c = np.load(cp, mmap_mode="r", allow_pickle=False)
        feature = np.load(base_directory / f"client_{i}_private.npy", mmap_mode="r", allow_pickle=False)
        if p.shape != (len(feature),) or p.dtype != np.int64 or np.any((p < 0) | (p >= cfg.classes)):
            raise ValueError(f"Invalid K-scaling pseudo-labels for client {i}")
        if c.shape != (cfg.classes, feature.shape[1]):
            raise ValueError(f"Invalid K-scaling centers for client {i}")
        if not np.isfinite(c).all() or record['client'] != i or record['n'] != len(feature) or record['pseudo_histogram'] != np.bincount(p, minlength=cfg.classes).tolist():
            raise ValueError('K-scaling client statistics mismatch')
        for filename, path in ((f"client_{i}_pseudo.npy", pp), (f"client_{i}_centers.npy", cp)):
            if _sha(path) != meta.get("asset_hashes", {}).get(filename):
                raise ValueError(f"K-scaling asset hash mismatch: {filename}")
    return meta


