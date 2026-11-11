"""STL-10 binary reader and private-only autoencoder feature preparation."""
from pathlib import Path
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import tarfile
import time
import urllib.request

import numpy as np
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits

from experiments.noniid_clustering.data import partition_indices
from experiments.quantity_heterogeneity.partition import partition_indices as quantity_partition

PARTITION_IDENTITY = "quantity-capacity-ipf-residual-flow-v1"


def _capacities(cfg, profile):
    smoke = cfg.train_limit - cfg.public_pool == 192
    total = 192 if smoke else 2400
    values = {"equal": [total // 6] * 6,
              "moderate": ([16,32,48]*2 if smoke else [200,400,600]*2),
              "strong": ([10,32,54]*2 if smoke else [100,400,700]*2)}
    if profile not in values or len(cfg.dimensions) != 6:
        raise ValueError("quantity heterogeneity requires six clients and equal/moderate/strong profile")
    return values[profile]

TARBALL = "stl10_binary.tar.gz"
TARBALL_MD5 = "91f7769df0f17e558f3565bffb0c7dfb"
URL = "https://cs.stanford.edu/~acoates/stl10/stl10_binary.tar.gz"
FILES = {
    "train_X.bin": "918c2871b30a85fa023e0c44e0bee87f",
    "train_y.bin": "5a34089d4802c674881badbb80307741",
    "unlabeled_X.bin": "5242ba1fed5e4be9e1e742405eb56ca4",
    "test_X.bin": "7f263ba9f9e0b06b93213547f721ac82",
    "test_y.bin": "36f9794fa4beb8a2c72628de14fa638e",
}


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def md5(path):
    h = hashlib.md5()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_hashes():
    return {p.name: sha(p) for p in sorted(Path(__file__).parent.glob("*.py"))}


def read_images(path):
    raw = np.fromfile(path, dtype=np.uint8)
    if len(raw) % (3 * 96 * 96):
        raise ValueError(f"Invalid STL-10 binary image file: {path}")
    # Match torchvision's load transform exactly, including the spatial transpose.
    return raw.reshape(-1, 3, 96, 96).transpose(0, 1, 3, 2)


def resize_area32(images):
    """Exact 3x3 box/area mean; produce flattened RGB pixels in [0,1]."""
    a = np.asarray(images)
    if a.ndim != 4 or a.shape[1:] != (3, 96, 96):
        raise ValueError("Expected STL-10 images shaped (N,3,96,96)")
    return a.reshape(len(a), 3, 32, 3, 32, 3).mean(axis=(3, 5), dtype=np.float32).reshape(len(a), 3072).astype(np.float32) / np.float32(255)


def read_labels(path):
    y = np.fromfile(path, dtype=np.uint8)
    if np.any((y < 1) | (y > 10)):
        raise ValueError("Invalid STL-10 labels")
    return y.astype(np.int64) - 1


def ensure_data(data_dir, download=False, timing=None):
    root = Path(data_dir)
    base = root / "stl10_binary"
    base.mkdir(parents=True, exist_ok=True)
    if not all((base / name).is_file() for name in FILES):
        archive = root / TARBALL
        if not archive.exists():
            if not download:
                raise FileNotFoundError(f"Missing STL-10 binary files under {base}")
            part = archive.with_suffix(archive.suffix + ".part")
            if part.exists():
                raise FileExistsError(f"Incomplete archive exists: {part}")
            download_started = time.perf_counter()
            urllib_error = None
            part_owned = False
            try:
                with urllib.request.urlopen(URL, timeout=180) as response:
                    with part.open("xb") as out:
                        part_owned = True
                        for block in iter(lambda: response.read(1024 * 1024), b""):
                            out.write(block)
            except Exception as exc:
                urllib_error = exc
                # This path is ours: remove only the incomplete .part from this attempt.
                if part_owned and part.exists():
                    part.unlink()
                curl = shutil.which("curl.exe")
                if not curl:
                    raise RuntimeError(f"STL-10 HTTPS download failed and curl.exe is unavailable: {exc}") from exc
                try:
                    part.open("xb").close()  # reserve an empty path owned by this download attempt
                    part_owned = True
                except FileExistsError as reserve_exc:
                    raise RuntimeError(f"Refusing to overwrite an existing partial archive: {part}") from reserve_exc
                try:
                    result = subprocess.run([curl, "--fail", "--location", "--retry", "2",
                                             "--output", str(part), URL], capture_output=True,
                                            text=True, check=False)
                    if result.returncode != 0:
                        raise RuntimeError(f"curl.exe exited {result.returncode}: {result.stderr[-1000:]}")
                except Exception as fallback_exc:
                    if part_owned and part.exists():
                        part.unlink()
                    raise RuntimeError(f"STL-10 HTTPS download failed via urllib ({urllib_error}) and curl.exe ({fallback_exc})") from fallback_exc
            if timing is not None:
                timing["download_seconds"] = timing.get("download_seconds", 0.0) + time.perf_counter() - download_started
            if md5(part) != TARBALL_MD5:
                part.unlink(missing_ok=True)
                raise ValueError("Official STL-10 tarball MD5 mismatch")
            part.replace(archive)
        if md5(archive) != TARBALL_MD5:
            raise ValueError("Official STL-10 tarball MD5 mismatch")
        # Extract exactly the five image/label files; never trust archive paths.
        with tarfile.open(archive, "r:gz") as tf:
            members = {}
            for m in tf.getmembers():
                name = Path(m.name).name
                if name in FILES:
                    if not m.isfile() or name in members:
                        raise ValueError("Unsafe or duplicate STL-10 archive member")
                    members[name] = m
            if set(members) != set(FILES):
                raise ValueError("STL-10 archive is missing required files")
            for name, member in members.items():
                source = tf.extractfile(member)
                target = base / name
                with target.open("wb") as out:
                    while block := source.read(1024 * 1024):
                        out.write(block)
    for name, checksum in FILES.items():
        path = base / name
        if md5(path) != checksum:
            raise ValueError(f"Official STL-10 member MD5 mismatch: {name}")
    return base


def create_fixture(root):
    """Create small genuine-format STL binary files for tests/smoke runs."""
    base = Path(root) / "stl10_binary"
    base.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261101)
    for name, count in (("train_X.bin", 256), ("unlabeled_X.bin", 256), ("test_X.bin", 64)):
        (base / name).write_bytes(rng.integers(0, 256, size=(count, 3, 96, 96), dtype=np.uint8).tobytes())
    (base / "train_y.bin").write_bytes((np.arange(256, dtype=np.uint8) % 10 + 1).tobytes())
    (base / "test_y.bin").write_bytes((np.arange(64, dtype=np.uint8) % 10 + 1).tobytes())
    return base


def preparation_identity():
    return {"code": {"data.py": sha(Path(__file__))},
            "partition_code": sha(Path(__import__("experiments.noniid_clustering.data", fromlist=["x"]).__file__)),
            "dependencies": {n: importlib.metadata.version(n) for n in ("numpy", "torch", "scikit-learn", "scipy", "threadpoolctl")}}


def _key(cfg, seed, partition, fixture, source_hashes, profile, capacities):
    value = {"config": cfg.preparation(), "seed": int(seed), "partition": partition,
             "fixture": bool(fixture), "profile": profile, "capacities": capacities,
             "quantity_partition_identity": {"algorithm": PARTITION_IDENTITY,
                 "source_sha256": sha(Path(__import__("experiments.quantity_heterogeneity.partition", fromlist=["x"]).__file__))},
             "identity": preparation_identity(), "format": 2,
             "official_checksums": None if fixture else {"tar_md5": TARBALL_MD5, "files": FILES},
             "source_sha256": source_hashes}
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def prepare(cache, data_dir, spec, seed, partition, *, profile, fixture=False, download=False, source_results=None):
    cfg = spec.config
    cfg.validate()
    started = time.perf_counter()
    download_timing = {}
    if fixture:
        base = create_fixture(data_dir)
    else:
        base = ensure_data(data_dir, download, timing=download_timing)
    original_hashes = {p.name: sha(p) for p in sorted(base.iterdir()) if p.name in FILES}
    capacities = _capacities(cfg, profile)
    n_private = cfg.train_limit - cfg.public_pool
    if n_private != sum(capacities):
        raise ValueError(f"config private total {n_private} does not match {profile} capacities {sum(capacities)}")
    if profile == "equal" and not fixture:
        candidate = Path(source_results) if source_results is not None else Path(__file__).parents[1] / "lr_client_scaling" / "results_full_fixed_per_client"
        pointer = candidate / "inputs" / f"{int(seed)}_{partition}_fixed_per_client_6.json"
        if not pointer.is_file():
            raise FileNotFoundError(f"Required P3 equal-profile input pointer is missing: {pointer}")
        try:
            record=json.loads(pointer.read_text(encoding="utf-8"))
            target=Path(record["path"])
            expected_meta_sha=record["metadata_sha256"]
        except Exception as exc:
            raise ValueError(f"Invalid P3 input pointer: {pointer}") from exc
        marker=target / "prepared.json"
        if not marker.is_file() or sha(marker) != expected_meta_sha:
            raise ValueError(f"P3 prepared metadata digest mismatch: {marker}")
        verify(target, spec, seed, partition, profile=profile, fixture=False)
        return target
    directory = Path(cache) / f"seed_{seed}_{profile}_{partition}_{_key(cfg, seed, partition, fixture, original_hashes, profile, capacities)}"
    marker = directory / "prepared.json"
    if marker.exists():
        verify(directory, spec, seed, partition, profile=profile, fixture=fixture)
        return directory
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Partial preparation cache: {directory}")
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    from torch import nn
    import torch.nn.functional as F
    torch.set_num_threads(cfg.prepare_threads)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(cfg.threads))
    device = torch.device(cfg.prepare_device)
    directory.mkdir(parents=True, exist_ok=True)
    train = resize_area32(read_images(base / "train_X.bin"))
    labels = read_labels(base / "train_y.bin")
    test = resize_area32(read_images(base / "test_X.bin"))[:cfg.test_limit]
    test_labels = read_labels(base / "test_y.bin")[:cfg.test_limit]
    if fixture:
        n_private = min(n_private, 256)
    if n_private < 1 or n_private > len(train):
        raise ValueError("STL-10 train limit exceeds available labeled images")
    train, labels = train[:n_private], labels[:n_private]
    if len(test) < cfg.test_limit:
        raise ValueError("STL-10 test limit exceeds available test images")
    if fixture and cfg.public_pool > 256:
        raise ValueError("Fixture has only 256 unlabeled images")
    unlabeled_path = base / "unlabeled_X.bin"
    unlabeled_count = unlabeled_path.stat().st_size // (3 * 96 * 96)
    if unlabeled_path.stat().st_size % (3 * 96 * 96):
        raise ValueError("Invalid STL-10 unlabeled binary length")
    if cfg.public_pool > unlabeled_count:
        raise ValueError("STL-10 public pool exceeds available unlabeled images")
    public_ids = np.random.default_rng(np.random.SeedSequence([int(seed), 510])).permutation(unlabeled_count)[:cfg.public_pool]
    public_raw = np.memmap(unlabeled_path, dtype=np.uint8, mode="r").reshape(-1, 3, 96, 96)
    pub_images = resize_area32(public_raw.transpose(0, 1, 3, 2)[public_ids])
    del public_raw
    _, private_ids, diagnostics = quantity_partition(labels, 0, len(cfg.dimensions), int(seed), partition, capacities)
    np.save(directory / "public_ids.npy", public_ids)
    np.save(directory / "test_labels.npy", test_labels)
    (directory / "partition.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    records = []
    class AE(nn.Module):
        def __init__(self, width):
            super().__init__(); self.encoder = nn.Linear(3072, width); self.decoder = nn.Linear(width, 3072)
        def encode(self, x): return F.normalize(F.relu(self.encoder(x)), p=2, dim=1, eps=1e-12)
        def forward(self, x): return torch.sigmoid(self.decoder(F.relu(self.encoder(x))))
    for client, (width, ids) in enumerate(zip(cfg.dimensions, private_ids)):
        torch.manual_seed(int(np.random.SeedSequence([int(seed), 220, client]).generate_state(1)[0]))
        model = AE(width).to(device); opt = torch.optim.Adam(model.parameters(), lr=cfg.pretrain_lr)
        noise_gen = torch.Generator(device=device).manual_seed(int(seed) * 1000 + client + 271)
        losses = []
        if device.type == "cuda": torch.cuda.synchronize(device)
        t0 = time.perf_counter()
        for epoch in range(cfg.pretrain_epochs):
            order = np.random.default_rng(np.random.SeedSequence([int(seed), 221, client, epoch])).permutation(ids)
            loss_sum = 0.
            for off in range(0, len(order), cfg.pretrain_batch):
                batch = torch.as_tensor(train[order[off:off+cfg.pretrain_batch]], device=device)
                noisy = (batch + torch.randn(batch.shape, generator=noise_gen, device=device) * cfg.noise_std).clamp(0, 1)
                opt.zero_grad(set_to_none=True); loss = F.mse_loss(model(noisy), batch); loss.backward(); opt.step()
                loss_sum += float(loss.detach()) * len(batch)
            losses.append(loss_sum / len(ids))
        if device.type == "cuda": torch.cuda.synchronize(device)
        pretrain_s = time.perf_counter() - t0; model.eval().requires_grad_(False)
        torch.save(model.state_dict(), directory / f"client_{client}_autoencoder.pt")
        np.save(directory / f"client_{client}_private_ids.npy", ids)
        def features(images, selected, name):
            out = np.lib.format.open_memmap(directory / name, mode="w+", dtype=np.float32, shape=(len(selected), width))
            with torch.no_grad():
                for off in range(0, len(selected), cfg.feature_batch):
                    x = torch.as_tensor(images[selected[off:off+cfg.feature_batch]], device=device)
                    out[off:off+len(x)] = model.encode(x).cpu().numpy()
            out.flush(); del out
        features(train, ids, f"client_{client}_private.npy")
        features(pub_images, np.arange(len(pub_images)), f"client_{client}_public.npy")
        features(test, np.arange(len(test)), f"client_{client}_test.npy")
        z = np.load(directory / f"client_{client}_private.npy", mmap_mode="r", allow_pickle=False)
        with threadpool_limits(limits=cfg.threads):
            km = KMeans(n_clusters=cfg.classes, n_init=cfg.kmeans_restarts, max_iter=cfg.kmeans_max_iter, random_state=int(seed)+client*101)
            pseudo = km.fit_predict(z)
        np.save(directory / f"client_{client}_pseudo.npy", pseudo.astype(np.int64)); np.save(directory / f"client_{client}_centers.npy", km.cluster_centers_)
        records.append({"client": client, "width": width, "private_samples": len(ids), "pretrain_losses": losses,
                        "pretrain_seconds": pretrain_s, "pseudo_histogram": np.bincount(pseudo, minlength=cfg.classes).tolist(), "encoder_frozen": True})
    if device.type == "cuda": torch.cuda.synchronize(device)
    metadata = {"dataset": "STL-10 fixture" if fixture else "STL-10", "seed": int(seed), "partition": partition,
                "profile": profile, "target_capacities": capacities,
                "quantity_partition_identity": {"algorithm": PARTITION_IDENTITY,
                    "source_sha256": sha(Path(__import__("experiments.quantity_heterogeneity.partition", fromlist=["x"]).__file__))},
                "config": cfg.preparation(), "preparation_identity": preparation_identity(), "clients": records,
                "source_md5": ({"fixture": True} if fixture else {"tarball": TARBALL_MD5, "files": FILES}),
                "source_sha256": original_hashes,
                "source_directory": str(base.resolve()),
                "preparation_wall_seconds_excluding_download": time.perf_counter()-started-download_timing.get("download_seconds", 0.0),
                "download_seconds_excluded": download_timing.get("download_seconds", 0.0),
                "files": {p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file()}}
    (directory / "prepared.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return directory


def verify(directory, spec, seed, partition, *, profile, fixture=False):
    cfg = spec.config if hasattr(spec, "config") else spec
    directory = Path(directory)
    legacy_marker = directory / "prepared.json"
    if profile == "equal" and legacy_marker.is_file():
        legacy_meta = json.loads(legacy_marker.read_text(encoding="utf-8"))
        if "profile" not in legacy_meta:
            # P3 equal preparations are immutable inputs and retain their own
            # original verifier and manifest schema.
            from experiments.stl10_transfer.data import verify as legacy_verify
            legacy_verify(directory, cfg, seed, partition, fixture=fixture)
            _verify_shapes(directory, cfg, _capacities(cfg, "equal"))
            return True
    meta = json.loads((directory / "prepared.json").read_text(encoding="utf-8"))
    capacities = _capacities(cfg, profile)
    if meta.get("dataset") != ("STL-10 fixture" if fixture else "STL-10") or meta.get("config") != cfg.preparation() or meta.get("seed") != int(seed) or meta.get("partition") != partition or meta.get("profile") != profile or meta.get("target_capacities") != capacities:
        raise ValueError("Prepared STL-10 metadata mismatch")
    if meta.get("preparation_identity") != preparation_identity():
        raise ValueError("Prepared STL-10 source/runtime identity mismatch")
    expected_qid = {"algorithm": PARTITION_IDENTITY,
                    "source_sha256": sha(Path(__import__("experiments.quantity_heterogeneity.partition", fromlist=["x"]).__file__))}
    if meta.get("quantity_partition_identity") != expected_qid:
        raise ValueError("Prepared quantity partition source identity mismatch")
    base = Path(meta.get("source_directory", ""))
    source_sha = meta.get("source_sha256", {})
    source_md5 = meta.get("source_md5")
    if set(source_sha) != set(FILES):
        raise ValueError("STL-10 source manifest must name exactly five official assets")
    if fixture:
        if source_md5 != {"fixture": True}:
            raise ValueError("Fixture source identity mismatch")
    elif source_md5 != {"tarball": TARBALL_MD5, "files": FILES}:
        raise ValueError("Official STL-10 checksum identity mismatch")
    for name, digest in source_sha.items():
        if Path(name).name != name or sha(base / name) != digest:
            raise ValueError(f"STL-10 source asset hash mismatch: {name}")
    files = meta.get("files", {})
    actual = {p.name for p in directory.iterdir() if p.is_file() and p.name != "prepared.json"}
    if set(files) != actual:
        raise ValueError("Prepared STL-10 asset manifest mismatch")
    for name, digest in files.items():
        if Path(name).name != name or sha(directory / name) != digest:
            raise ValueError(f"Prepared STL-10 hash mismatch: {name}")
    pub = np.load(directory / "public_ids.npy", allow_pickle=False)
    priv = [np.load(directory / f"client_{i}_private_ids.npy", allow_pickle=False) for i in range(len(cfg.dimensions))]
    private_joined = np.concatenate(priv)
    if len(np.unique(pub)) != len(pub) or len(np.unique(private_joined)) != len(private_joined):
        raise ValueError("STL-10 public or private split contains duplicate indices")
    expected_sizes = capacities
    if len(pub) != cfg.public_pool or [len(x) for x in priv] != expected_sizes:
        raise ValueError("STL-10 split counts mismatch")
    source_count = (base / "unlabeled_X.bin").stat().st_size // (3 * 96 * 96)
    expected_public = np.random.default_rng(np.random.SeedSequence([int(seed), 510])).permutation(source_count)[:cfg.public_pool]
    if not np.array_equal(pub, expected_public) or np.any((pub < 0) | (pub >= source_count)):
        raise ValueError("STL-10 public ID sampling mismatch")
    train_count = cfg.train_limit - cfg.public_pool
    if np.any((private_joined < 0) | (private_joined >= train_count)) or len(np.unique(private_joined)) != train_count:
        raise ValueError("STL-10 private IDs fail range/coverage audit")
    labels = read_labels(base / "train_y.bin")[:train_count]
    _, expected_private, expected_diagnostics = quantity_partition(labels, 0, len(cfg.dimensions), int(seed), partition, capacities)
    if any(not np.array_equal(a, b) for a, b in zip(priv, expected_private)):
        raise ValueError("STL-10 private partition does not reproduce")
    diagnostics_path = directory / "partition.json"
    try:
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError("Invalid STL-10 partition diagnostics") from exc
    if diagnostics != expected_diagnostics:
        raise ValueError("STL-10 partition diagnostics mismatch")
    _verify_shapes(directory, cfg, capacities)
    return True


def _verify_shapes(directory, cfg, capacities):
    """Audit tensor dimensions as well as the hashed file manifest."""
    directory = Path(directory)
    meta=json.loads((directory/"prepared.json").read_text(encoding="utf-8"))
    records=meta.get("clients", [])
    if len(records) != len(capacities):
        raise ValueError("Prepared client metadata count mismatch")
    for i,(record,width,count) in enumerate(zip(records,cfg.dimensions,capacities)):
        if (record.get("client") != i or record.get("width") != width
                or record.get("private_samples") != count or record.get("encoder_frozen") is not True):
            raise ValueError(f"Prepared client metadata mismatch: client {i}")
    test_labels=np.load(directory/"test_labels.npy",allow_pickle=False)
    if test_labels.shape != (cfg.test_limit,) or not np.issubdtype(test_labels.dtype,np.integer) or np.any((test_labels<0)|(test_labels>9)):
        raise ValueError("Prepared test labels shape/range mismatch")
    for i, (width, count) in enumerate(zip(cfg.dimensions, capacities)):
        expected = {f"client_{i}_private.npy": (count, width),
                    f"client_{i}_public.npy": (cfg.public_pool, width),
                    f"client_{i}_test.npy": (cfg.test_limit, width),
                    f"client_{i}_pseudo.npy": (count,),
                    f"client_{i}_centers.npy": (cfg.classes, width)}
        for name, shape in expected.items():
            arr=np.load(directory/name, mmap_mode="r", allow_pickle=False)
            try:
                if arr.shape != shape:
                    raise ValueError(f"Prepared feature shape mismatch: {name} {arr.shape} != {shape}")
                if name.endswith("_pseudo.npy") and (arr.dtype != np.int64 or np.any(arr < 0) or np.any(arr >= cfg.classes)):
                    raise ValueError(f"Prepared pseudo-label dtype/range mismatch: {name}")
                if name.endswith("_pseudo.npy"):
                    observed=np.bincount(arr,minlength=cfg.classes).astype(int).tolist()
                    if records[i].get("pseudo_histogram") != observed:
                        raise ValueError(f"Prepared pseudo-label histogram mismatch: client {i}")
            finally:
                mmap=getattr(arr, "_mmap", None)
                if mmap is not None: mmap.close()
