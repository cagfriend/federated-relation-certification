"""Preparation and audit helpers for STL-10 client-count scaling."""
import hashlib
import json
import time
from pathlib import Path

import numpy as np

from experiments.stl10_transfer import data as transfer_data
from experiments.stl10_compute.design import plan as compute_plan


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _source_reusable(cfg, seed, partition, fixture, source_results):
    """Find an old compute artifact only when it is precisely the N=6 full plan."""
    if fixture or source_results is None:
        return None
    original = compute_plan("full")[0].config
    if cfg.preparation() != original.preparation():
        return None
    marker = Path(source_results) / f"prepared_{partition}_seed_{seed}.json"
    if not marker.is_file():
        return None
    ref = json.loads(marker.read_text(encoding="utf-8"))
    directory = Path(ref["path"])
    metadata = directory / "prepared.json"
    if not metadata.is_file() or _sha(metadata) != ref["metadata_sha256"]:
        raise ValueError('Historical N6 preparation digest mismatch')
    transfer_data.verify(directory, cfg, seed, partition, fixture=False)
    return directory


def prepare(cache, data_dir, spec, seed, partition, *, fixture=False,
            download=False, source_results=None) -> Path:
    cfg = spec.config
    spec.validate()
    started = time.perf_counter()
    print(f"[client-scaling data] prepare start seed={seed} partition={partition} clients={len(cfg.dimensions)}", flush=True)
    reused = _source_reusable(cfg, seed, partition, fixture, source_results)
    if reused is not None:
        print(f"[client-scaling data] reusing verified preparation: {reused}", flush=True)
        result = reused
    else:
        result = transfer_data.prepare(cache, data_dir, cfg, seed, partition,
                                       download=download, fixture=fixture)
    verify(result, spec, seed, partition, fixture=fixture)
    print(f"[client-scaling data] prepare complete in {time.perf_counter()-started:.1f}s: {result}", flush=True)
    return Path(result)


def verify(directory, spec, seed, partition, *, fixture=False) -> dict:
    cfg = spec.config
    if cfg.classes != 10:
        raise ValueError('Client scaling requires K=10')
    directory = Path(directory)
    transfer_data.verify(directory, cfg, seed, partition, fixture=fixture)
    meta = json.loads((directory / "prepared.json").read_text(encoding="utf-8"))
    clients = len(cfg.dimensions)
    if clients % 2 or len(set(cfg.dimensions)) != 2:
        raise ValueError("Client scaling expects an even number of clients split across two widths")
    widths = sorted(set(cfg.dimensions))
    if cfg.dimensions.count(widths[0]) != clients // 2 or cfg.dimensions.count(widths[1]) != clients // 2:
        raise ValueError("Client scaling must use equal counts of the small and large widths")
    total = cfg.train_limit - cfg.public_pool
    records = meta.get("clients")
    if not isinstance(records, list) or len(records) != clients:
        raise ValueError("Prepared client metadata count mismatch")
    all_ids = []
    for client, (width, record) in enumerate(zip(cfg.dimensions, records)):
        ids = np.load(directory / f"client_{client}_private_ids.npy", allow_pickle=False)
        pseudo = np.load(directory / f"client_{client}_pseudo.npy", allow_pickle=False)
        if ids.ndim != 1 or len(ids) != int(record.get("private_samples", -1)):
            raise ValueError(f"Client {client} private sample count mismatch")
        if pseudo.shape != (len(ids),) or pseudo.dtype != np.int64 or np.any((pseudo < 0) | (pseudo >= 10)):
            raise ValueError(f"Client {client} pseudo-label shape or range mismatch")
        if record.get("width") != width or record.get("pseudo_histogram") != np.bincount(pseudo, minlength=10).tolist():
            raise ValueError(f"Client {client} metadata does not match its pseudo-labels")
        centers = np.load(directory / f"client_{client}_centers.npy", mmap_mode="r", allow_pickle=False)
        if centers.shape != (10, width) or not np.isfinite(centers).all():
            raise ValueError(f"Client {client} must have 10 cluster centers of its configured width")
        all_ids.append(ids)
    joined = np.concatenate(all_ids)
    if len(joined) != total or len(np.unique(joined)) != total or not np.array_equal(np.sort(joined), np.arange(total)):
        raise ValueError("Client private IDs must uniquely cover 0..total-1")
    return {"valid": True, "clients": clients, "private_total": total,
            "widths": {str(w): cfg.dimensions.count(w) for w in widths},
            "clusters_per_client": 10}
