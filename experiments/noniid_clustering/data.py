"""Label-aware partitioning and isolated preparation for non-IID clustering runs.

Labels are used only to construct and audit the partition.  Feature preparation,
autoencoder training, KMeans, and pseudo-label generation remain in
``experiments.public_scaling.data`` and receive image IDs only.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import urllib.request

import numpy as np

PARTITIONS = ("iid", "dirichlet_0.5", "dirichlet_0.1")
ORIGIN = "https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/"
# MD5 values published in zalandoresearch/fashion-mnist README.md.
FILES = {
    "train-images-idx3-ubyte.gz": "8d4fb7e6c68d591d4c3dfef9ec88bf0d",
    "train-labels-idx1-ubyte.gz": "25c81989df183df01b3e8a0aad5dffbe",
    "t10k-images-idx3-ubyte.gz": "bef4ecab320f06d8554ea6380940ec79",
    "t10k-labels-idx1-ubyte.gz": "bb300cfdad3c16e7a12a480ee83cd310",
}


def _file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def ensure_data(data_dir, download=False):
    """Ensure all four official IDX gzip assets, including training labels."""
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    for name, checksum in FILES.items():
        target = root / name
        if not target.exists():
            if not download:
                raise FileNotFoundError(f"Missing {target}; use --download or provide official IDX files")
            temporary = target.with_suffix(target.suffix + ".part")
            if temporary.exists():
                raise FileExistsError(f"Incomplete download exists: {temporary}; inspect/remove before retrying")
            print(f"Downloading official Fashion-MNIST: {name}", flush=True)
            with urllib.request.urlopen(ORIGIN + name, timeout=120) as response, temporary.open("xb") as handle:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    handle.write(block)
            if _file_md5(temporary) != checksum:
                raise ValueError(f"Official checksum mismatch: {temporary}")
            temporary.rename(target)
        if _file_md5(target) != checksum:
            raise ValueError(f"Official checksum mismatch: {target}")
    return root


def _partition_seed(seed: int) -> np.random.Generator:
    return np.random.default_rng(np.random.SeedSequence([int(seed), 210]))


def _ipf(weights: np.ndarray, row_totals: np.ndarray, col_totals: np.ndarray) -> np.ndarray:
    """Fit positive client/class weights to exact row and column margins."""
    x = np.asarray(weights, dtype=np.float64).copy()
    rows = np.asarray(row_totals, dtype=np.float64)
    cols = np.asarray(col_totals, dtype=np.float64)
    if not np.isclose(rows.sum(), cols.sum()):
        raise ValueError("Inconsistent transportation margins")
    active_cols = cols > 0
    x[:, ~active_cols] = 0.0
    x[:, active_cols] = np.maximum(x[:, active_cols], np.finfo(np.float64).tiny)
    for _ in range(10000):
        x *= np.divide(rows, x.sum(axis=1), out=np.ones_like(rows), where=x.sum(axis=1) > 0)[:, None]
        sums = x.sum(axis=0)
        scale = np.divide(cols, sums, out=np.zeros_like(cols), where=sums > 0)
        x *= scale[None, :]
        err = max(float(np.max(np.abs(x.sum(axis=1) - rows))),
                  float(np.max(np.abs(x.sum(axis=0) - cols))))
        if err < 1e-8:
            return x
    raise RuntimeError("IPF did not converge for requested partition margins")


def _integerize(fitted: np.ndarray, row_totals: np.ndarray, col_totals: np.ndarray) -> np.ndarray:
    """Floor the IPF table, then solve a 0/1 residual bipartite flow."""
    base = np.floor(fitted).astype(np.int64)
    row_need = np.asarray(row_totals, dtype=np.int64) - base.sum(axis=1)
    col_need = np.asarray(col_totals, dtype=np.int64) - base.sum(axis=0)
    if np.any(row_need < 0) or np.any(col_need < 0):
        raise RuntimeError("IPF floor exceeded a requested margin")
    if int(row_need.sum()) != int(col_need.sum()):
        raise RuntimeError("Integer residual margins do not balance")
    if not row_need.sum():
        return base

    # The fractional part is a feasible fractional bipartite flow with these
    # integer margins. The transportation polytope is integral, so HiGHS LP
    # returns an integral vertex without a costly general MILP.
    from scipy.optimize import linprog

    clients, classes = fitted.shape
    frac = (fitted - base).ravel()
    equality = np.zeros((clients + classes, clients * classes), dtype=np.float64)
    for i in range(clients):
        equality[i, i * classes:(i + 1) * classes] = 1.0
    for j in range(classes):
        equality[clients + j, j::classes] = 1.0
    rhs = np.concatenate((row_need, col_need)).astype(np.float64)
    solution = linprog(-frac, A_eq=equality, b_eq=rhs,
                       bounds=(0, 1), method="highs")
    if not solution.success:
        raise RuntimeError(f"Residual transportation solve failed: {solution.message}")
    residual = solution.x.reshape(clients, classes)
    rounded = np.rint(residual).astype(np.int64)
    if (np.max(np.abs(residual - rounded)) > 1e-6
            or not np.array_equal(rounded.sum(axis=1), row_need)
            or not np.array_equal(rounded.sum(axis=0), col_need)):
        raise RuntimeError("Residual solver did not return a valid 0/1 transportation flow")
    return base + rounded


def _diagnostics(private_ids, labels, clients, public_ids, partition, alpha=None):
    n_classes = 10
    histograms = []
    entropies = []
    missing = []
    for ids in private_ids:
        hist = np.bincount(labels[ids].astype(np.int64), minlength=n_classes)
        probabilities = hist[hist > 0] / max(1, len(ids))
        histograms.append(hist.astype(int).tolist())
        entropies.append(float(-np.sum(probabilities * np.log(probabilities))))
        missing.append(np.flatnonzero(hist == 0).astype(int).tolist())
    total_hist = np.bincount(labels[np.concatenate(private_ids)].astype(np.int64), minlength=n_classes)
    return {
        "partition": partition,
        "alpha": alpha,
        "public_count": int(len(public_ids)),
        "private_count": int(sum(map(len, private_ids))),
        "client_counts": [int(len(ids)) for ids in private_ids],
        "client_class_histograms": histograms,
        "client_entropy_nats": entropies,
        "client_missing_classes": missing,
        "private_class_totals": total_hist.astype(int).tolist(),
    }


def partition_indices(labels, public_pool, clients, seed, partition):
    """Return shared public IDs and equal-capacity private client IDs.

    Dirichlet draws provide client/class affinities. IPF matches those affinities
    to exact client capacities and private class totals; a residual flow
    integerizes the fitted table before class-wise sample IDs are shuffled out.
    """
    y = np.asarray(labels)
    if y.ndim != 1 or len(y) == 0 or not np.issubdtype(y.dtype, np.integer):
        raise ValueError("labels must be a nonempty one-dimensional integer array")
    if np.any((y < 0) | (y > 9)):
        raise ValueError("Fashion-MNIST labels must be in [0, 9]")
    if partition not in PARTITIONS:
        raise ValueError(f"Unknown partition {partition!r}; expected one of {PARTITIONS}")
    if not isinstance(clients, int) or clients < 1:
        raise ValueError("clients must be a positive integer")
    if not isinstance(public_pool, int) or not 0 <= public_pool < len(y):
        raise ValueError("public_pool must leave at least one private sample")
    rng = _partition_seed(seed)
    order = rng.permutation(len(y))
    public_ids = order[:public_pool].astype(np.int64)
    private_universe = order[public_pool:].astype(np.int64)
    sizes = np.array([len(x) for x in np.array_split(private_universe, clients)], dtype=np.int64)

    if partition == "iid":
        # Match the established public_scaling implementation exactly.
        from experiments.public_scaling.data import split_indices
        old_public, old_private = split_indices(len(y), public_pool, clients, int(seed))
        if not np.array_equal(public_ids, old_public):
            raise RuntimeError("Public-ID generator diverged from public_scaling IID baseline")
        result = [np.asarray(ids, dtype=np.int64) for ids in old_private]
        diagnostics = _diagnostics(result, y, clients, public_ids, partition)
    else:
        alpha = 0.5 if partition == "dirichlet_0.5" else 0.1
        labels_private = y[private_universe].astype(np.int64)
        class_totals = np.bincount(labels_private, minlength=10).astype(np.int64)
        affinity = rng.dirichlet(np.full(10, alpha, dtype=np.float64), size=clients)
        fitted = _ipf(affinity, sizes, class_totals)
        allocation = _integerize(fitted, sizes, class_totals)
        result = [np.empty(int(size), dtype=np.int64) for size in sizes]
        offsets = np.zeros(clients, dtype=np.int64)
        for cls in range(10):
            class_ids = private_universe[labels_private == cls].copy()
            rng.shuffle(class_ids)
            split_at = 0
            for client in range(clients):
                count = int(allocation[client, cls])
                if count:
                    selected = class_ids[split_at:split_at + count]
                    result[client][offsets[client]:offsets[client] + count] = selected
                    offsets[client] += count
                    split_at += count
            if split_at != len(class_ids):
                raise RuntimeError("Class-wise assignment did not consume all private examples")
        if not np.array_equal(offsets, sizes):
            raise RuntimeError("Class-wise assignment did not fill exact client capacities")
        for ids in result:
            rng.shuffle(ids)
        diagnostics = _diagnostics(result, y, clients, public_ids, partition, alpha)
        diagnostics["allocation_matrix"] = allocation.astype(int).tolist()
        diagnostics["ipf_expected_matrix"] = fitted.tolist()

    joined = np.concatenate([public_ids, *result])
    if len(joined) != len(y) or len(np.unique(joined)) != len(y):
        raise RuntimeError("Public/private partition failed disjoint full-coverage audit")
    diagnostics["indices_sha256"] = hashlib.sha256(joined.astype("<i8", copy=False).tobytes()).hexdigest()
    return public_ids, result, diagnostics


def _partition_root(cache, partition):
    digest = _file_sha256(Path(__file__))[:16]
    return Path(cache) / f"noniid_{partition}_{digest}"


def prepare(cache, data_dir, config, seed, partition, download=False) -> Path:
    """Prepare core features with this partition in an isolated cache namespace."""
    if partition not in PARTITIONS:
        raise ValueError(f"Unknown partition {partition!r}")
    config.validate()
    from experiments.public_scaling import data as core

    ensure_data(data_dir, download)
    labels = core.idx(Path(data_dir) / "train-labels-idx1-ubyte.gz")[:config.train_limit]
    public_ids, private_ids, diagnostics = partition_indices(
        labels, config.public_pool, len(config.dimensions), seed, partition)
    root = _partition_root(cache, partition)
    root.mkdir(parents=True, exist_ok=True)

    # Detect interrupted wrapper completion before core.prepare can treat its
    # own prepared.json marker as a fully valid non-IID cache.
    expected_cache = core.preparation_key(config, seed)
    possible = root / f"seed_{seed}_{expected_cache}"
    if possible.exists() and (possible / "prepared.json").exists():
        old = json.loads((possible / "prepared.json").read_text(encoding="utf-8"))
        if not (old.get("partition_complete") is True
                and old.get("partition") == partition
                and (possible / "partition.json").is_file()):
            raise RuntimeError(f"Core preparation exists without completed partition wrapper: {possible}")

    original_split = core.split_indices
    def fixed_split(count, requested_pool, requested_clients, requested_seed):
        if (count != len(labels) or requested_pool != len(public_ids)
                or requested_clients != len(private_ids) or requested_seed != seed):
            raise ValueError("Core preparation requested an unexpected partition shape or identity")
        return public_ids, private_ids

    core.split_indices = fixed_split
    try:
        directory = Path(core.prepare(root, data_dir, config, seed, download=download))
    finally:
        core.split_indices = original_split

    marker_path = directory / "prepared.json"
    metadata = json.loads(marker_path.read_text(encoding="utf-8"))
    partition_file = directory / "partition.json"
    if metadata.get("partition_complete") is True:
        verify(directory, config, seed, partition)
        return directory
    if partition_file.exists():
        raise RuntimeError(f"Unregistered partition manifest exists; inspect cache: {partition_file}")

    private_names = []
    for client, ids in enumerate(private_ids):
        name = f"client_{client}_private_ids.npy"
        saved = np.load(directory / name, allow_pickle=False)
        if not np.array_equal(saved, ids):
            raise RuntimeError(f"Core preparation wrote unexpected private IDs for client {client}")
        private_names.append(name)
    saved_public = np.load(directory / "public_ids.npy", allow_pickle=False)
    if not np.array_equal(saved_public, public_ids):
        raise RuntimeError("Core preparation wrote unexpected public IDs")

    manifest = {
        "format": 1, "partition": partition, "seed": int(seed),
        "config": config.preparation(), "dataset": metadata.get("dataset"),
        "partition_algorithm": "dirichlet-affinity-ipf-integer-residual-flow" if partition.startswith("dirichlet") else "public_scaling.split_indices",
        "partition_module_sha256": _file_sha256(Path(__file__)),
        "source_indices": {
            "public_ids.npy": _file_sha256(directory / "public_ids.npy"),
            **{name: _file_sha256(directory / name) for name in private_names},
        },
        "diagnostics": diagnostics,
    }
    with partition_file.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
    metadata["partition"] = partition
    metadata["partition_manifest"] = "partition.json"
    metadata["partition_complete"] = True
    metadata["files"] = {p.name: _file_sha256(p) for p in sorted(directory.iterdir())
                          if p.is_file() and p.name != "prepared.json"}
    # Prepared marker is rewritten last and is the wrapper completion signal.
    temporary = marker_path.with_suffix(".json.part")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2, ensure_ascii=False)
    temporary.replace(marker_path)
    verify(directory, config, seed, partition)
    return directory


def verify(directory, config, seed, partition):
    """Verify prepared identity, wrapper completion, asset hashes and index coverage."""
    directory = Path(directory)
    marker_path = directory / "prepared.json"
    manifest_path = directory / "partition.json"
    if not marker_path.is_file() or not manifest_path.is_file():
        raise ValueError("Prepared non-IID cache is missing its completion markers")
    metadata = json.loads(marker_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (metadata.get("partition_complete") is not True or metadata.get("partition") != partition
            or metadata.get("seed") != seed or metadata.get("config") != config.preparation()
            or metadata.get("partition_manifest") != "partition.json"):
        raise ValueError("Prepared cache partition/config/seed identity mismatch")
    if (manifest.get("partition") != partition or manifest.get("seed") != seed
            or manifest.get("config") != config.preparation()
            or manifest.get("partition_module_sha256") != _file_sha256(Path(__file__))):
        raise ValueError("Partition manifest identity or implementation hash mismatch")
    for name, digest in metadata.get("files", {}).items():
        if Path(name).name != name or not (directory / name).is_file() or _file_sha256(directory / name) != digest:
            raise ValueError(f"Prepared asset hash mismatch: {name}")
    listed = set(metadata.get("files", {}))
    actual = {p.name for p in directory.iterdir() if p.is_file() and p.name != "prepared.json"}
    if not listed or listed != actual:
        raise ValueError("Prepared asset manifest is incomplete")
    for name, digest in manifest.get("source_indices", {}).items():
        if Path(name).name != name or _file_sha256(directory / name) != digest:
            raise ValueError(f"Partition index hash mismatch: {name}")

    public = np.load(directory / "public_ids.npy", allow_pickle=False)
    private = [np.load(directory / f"client_{i}_private_ids.npy", allow_pickle=False)
               for i in range(len(config.dimensions))]
    if len(public) != config.public_pool or any(len(x) != len(y) for x, y in zip(private, np.array_split(np.arange(config.train_limit-config.public_pool), len(private)))):
        raise ValueError("Prepared partition size mismatch")
    all_ids = np.concatenate([public, *private])
    if (len(all_ids) != config.train_limit or len(np.unique(all_ids)) != config.train_limit
            or int(all_ids.min()) < 0 or int(all_ids.max()) >= config.train_limit):
        raise ValueError("Prepared partition does not cover exactly the configured training index range")
    expected_public = _partition_seed(seed).permutation(config.train_limit)[:config.public_pool]
    if not np.array_equal(public, expected_public):
        raise ValueError("Prepared public pool does not match the seed-stable shared public IDs")
    expected_source_names = {"public_ids.npy"} | {
        f"client_{i}_private_ids.npy" for i in range(len(config.dimensions))}
    if set(manifest.get("source_indices", {})) != expected_source_names:
        raise ValueError("Partition manifest is missing client/public index hashes")
    hist = manifest.get("diagnostics", {}).get("client_class_histograms", [])
    if len(hist) != len(private) or any(len(row) != 10 or sum(row) != len(private[i])
                                        for i, row in enumerate(hist)):
        raise ValueError("Partition class histogram diagnostics are malformed")
    return True
