"""Official IDX data and private-only unlabeled frozen-feature preparation."""
from pathlib import Path
import gzip
import hashlib
import importlib.metadata
import json
import os
import struct
import time
import urllib.request

import numpy as np
from sklearn.cluster import KMeans
from threadpoolctl import threadpool_limits

from .graphs import make_graph

FILES = {
    "train-images-idx3-ubyte.gz": "8d4fb7e6c68d591d4c3dfef9ec88bf0d",
    "t10k-images-idx3-ubyte.gz": "bef4ecab320f06d8554ea6380940ec79",
    "t10k-labels-idx1-ubyte.gz": "bb300cfdad3c16e7a12a480ee83cd310",
}
# Official README supplies the checksums. Training true-label file is never read.
ORIGIN = "https://raw.githubusercontent.com/zalandoresearch/fashion-mnist/master/data/fashion/"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def json_write_new(path, data):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)


def source_hashes():
    folder = Path(__file__).parent
    return {p.name: sha(p) for p in sorted(folder.glob('*.py'))}


def runtime():
    import platform
    import sys
    from threadpoolctl import threadpool_info
    return {"python": sys.version, "executable": sys.executable, "numpy": np.__version__,
            "scipy": importlib.metadata.version("scipy"),
            "sklearn": importlib.metadata.version("scikit-learn"),
            "torch": importlib.metadata.version("torch"),
            "platform": platform.platform(), "blas": threadpool_info()}


def ensure_data(directory, download=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, checksum in FILES.items():
        target = directory / name
        if not target.exists():
            if not download:
                raise FileNotFoundError(f"Missing {target}; use --download or place official IDX gzip files here")
            temporary = target.with_suffix(target.suffix + ".part")
            if temporary.exists():
                raise FileExistsError(f"Incomplete download exists: {temporary}; inspect/remove it before retrying")
            print(f"Downloading official Fashion-MNIST: {name}", flush=True)
            with urllib.request.urlopen(ORIGIN + name, timeout=120) as response, temporary.open("xb") as handle:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    handle.write(block)
            if hashlib.md5(temporary.read_bytes()).hexdigest() != checksum:
                raise ValueError(f"Official checksum mismatch: {temporary}")
            temporary.rename(target)
        if hashlib.md5(target.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Official checksum mismatch: {target}")
    return directory


def idx(path):
    with gzip.open(path, "rb") as handle:
        payload = handle.read()
    magic = struct.unpack(">I", payload[:4])[0]
    if magic == 2051:
        count, rows, cols = struct.unpack(">III", payload[4:16])
        if (rows, cols) != (28, 28) or len(payload) != 16 + count * rows * cols:
            raise ValueError("Invalid Fashion-MNIST image IDX")
        return np.frombuffer(payload, dtype=np.uint8, offset=16).reshape(count, 784)
    if magic == 2049:
        count = struct.unpack(">I", payload[4:8])[0]
        if len(payload) != 8 + count:
            raise ValueError("Invalid label IDX")
        return np.frombuffer(payload, dtype=np.uint8, offset=8)
    raise ValueError("Invalid IDX magic")


def split_indices(count, public_pool, clients, seed):
    order = np.random.default_rng(np.random.SeedSequence([seed, 210])).permutation(count)
    public = order[:public_pool]
    private = list(np.array_split(order[public_pool:], clients))
    return public, private


def preparation_identity():
    return {"code": {"data.py": sha(Path(__file__))},
            "dependencies": {"numpy": np.__version__, **{name: importlib.metadata.version(name)
                             for name in ("torch", "scikit-learn", "scipy", "threadpoolctl")}}}


def preparation_key(config, seed):
    payload = {"config": config.preparation(), "seed": seed,
               "identity": preparation_identity(), "format": 3}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def prepare(cache, data_dir, config, seed, *, download=False):
    config.validate()
    directory = Path(cache) / f"seed_{seed}_{preparation_key(config, seed)}"
    marker = directory / "prepared.json"
    if marker.exists():
        metadata = json.loads(marker.read_text(encoding="utf-8"))
        if (metadata["config"] != config.preparation() or metadata["seed"] != seed
                or metadata["preparation_identity"] != preparation_identity()):
            raise ValueError("Prepared cache configuration mismatch")
        verify_prepared(directory, metadata)
        print(f"Reusing verified prepared features: {directory}", flush=True)
        return directory
    if directory.exists() and any(directory.iterdir()):
        raise FileExistsError(f"Partial preparation cache; inspect it or choose a new --cache: {directory}")
    ensure_data(data_dir, download)
    # This environment variable is set before importing torch/CUDA.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    from torch import nn
    import torch.nn.functional as functional
    if config.prepare_device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested for preparation but unavailable")
    torch.set_num_threads(config.prepare_threads)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    device = torch.device(config.prepare_device)
    directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    train = idx(Path(data_dir) / "train-images-idx3-ubyte.gz")[:config.train_limit]
    test = idx(Path(data_dir) / "t10k-images-idx3-ubyte.gz")[:config.test_limit]
    test_labels = idx(Path(data_dir) / "t10k-labels-idx1-ubyte.gz")[:config.test_limit]
    public_ids, private_ids = split_indices(len(train), config.public_pool, len(config.dimensions), seed)
    np.save(directory / "public_ids.npy", public_ids)
    np.save(directory / "test_labels.npy", test_labels)
    client_records = []

    def sync():
        if device.type == "cuda":
            torch.cuda.synchronize(device)

    class Autoencoder(nn.Module):
        def __init__(self, width):
            super().__init__()
            self.encoder = nn.Linear(784, width)
            self.decoder = nn.Linear(width, 784)

        def encode(self, x):
            return functional.normalize(functional.relu(self.encoder(x)), p=2, dim=1, eps=1e-12)

        def forward(self, x):
            return torch.sigmoid(self.decoder(functional.relu(self.encoder(x))))

    for client, (width, indices) in enumerate(zip(config.dimensions, private_ids)):
        print(f"Preparing seed={seed} client={client} width={width} private={len(indices)}", flush=True)
        torch.manual_seed(int(np.random.SeedSequence([seed, 220, client]).generate_state(1)[0]))
        model = Autoencoder(width).to(device)
        optimizer = torch.optim.Adam(model.parameters(), lr=config.pretrain_lr)
        noise_rng = torch.Generator(device=device).manual_seed(seed * 1000 + client + 271)
        losses = []
        sync()
        stage = time.perf_counter()
        model.train()
        for epoch in range(config.pretrain_epochs):
            order = np.random.default_rng(np.random.SeedSequence([seed, 221, client, epoch])).permutation(indices)
            loss_sum = 0.0
            for offset in range(0, len(order), config.pretrain_batch):
                ids = order[offset:offset + config.pretrain_batch]
                x = torch.tensor(train[ids], dtype=torch.float32, device=device) / 255
                noise = torch.randn(x.shape, device=device, generator=noise_rng) * config.noise_std
                optimizer.zero_grad(set_to_none=True)
                loss = functional.mse_loss(model((x + noise).clamp(0, 1)), x)
                loss.backward()
                optimizer.step()
                loss_sum += float(loss.detach().cpu()) * len(ids)
            losses.append(loss_sum / len(indices))
            print(f"  AE client={client} epoch={epoch + 1}/{config.pretrain_epochs} MSE={losses[-1]:.6f}", flush=True)
        sync()
        pretrain_s = time.perf_counter() - stage
        model.eval().requires_grad_(False)
        torch.save(model.state_dict(), directory / f"client_{client}_autoencoder.pt")

        def features(images, selected, name):
            sync()
            begin = time.perf_counter()
            output = np.lib.format.open_memmap(directory / name, mode="w+", dtype=np.float32,
                                               shape=(len(selected), width))
            with torch.no_grad():
                for offset in range(0, len(selected), config.feature_batch):
                    ids = selected[offset:offset + config.feature_batch]
                    x = torch.tensor(images[ids], dtype=torch.float32, device=device) / 255
                    output[offset:offset + len(ids)] = model.encode(x).cpu().numpy()
            output.flush()
            del output
            sync()
            return time.perf_counter() - begin

        np.save(directory / f"client_{client}_private_ids.npy", indices)
        private_s = features(train, indices, f"client_{client}_private.npy")
        public_s = features(train, public_ids, f"client_{client}_public.npy")
        test_s = features(test, np.arange(len(test)), f"client_{client}_test.npy")
        z = np.load(directory / f"client_{client}_private.npy", mmap_mode="r", allow_pickle=False)
        stage = time.perf_counter()
        os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(config.threads))
        with threadpool_limits(limits=config.threads):
            km = KMeans(n_clusters=config.classes, n_init=config.kmeans_restarts,
                        max_iter=config.kmeans_max_iter, random_state=seed + client * 101)
            labels = km.fit_predict(z)
        kmeans_s = time.perf_counter() - stage
        np.save(directory / f"client_{client}_pseudo.npy", labels.astype(np.int64))
        np.save(directory / f"client_{client}_centers.npy", km.cluster_centers_)
        client_records.append({"client": client, "width": width, "private_samples": len(indices),
                               "pretrain_losses": losses, "pretrain_seconds": pretrain_s,
                               "private_feature_seconds": private_s, "public_feature_seconds": public_s,
                               "test_feature_seconds": test_s, "kmeans_seconds": kmeans_s,
                               "pseudo_histogram": np.bincount(labels, minlength=config.classes).tolist(),
                               "encoder_frozen": True})
        del model, optimizer, km, z
        if device.type == "cuda":
            torch.cuda.empty_cache()
    metadata = {"dataset": "Fashion-MNIST", "seed": seed, "config": config.preparation(),
                "preparation_identity": preparation_identity(),
                "clients": client_records, "data_checksums_md5": FILES,
                "preparation_wall_seconds_excluding_download": time.perf_counter() - started,
                "preparation_scope": "private-only unlabeled AE pretraining, fixed private/public/test features, KMeans, writes; includes test feature preparation",
                "device": str(device), "torch": torch.__version__, "numpy": np.__version__,
                "files": {p.name: sha(p) for p in sorted(directory.iterdir()) if p.is_file()}}
    json_write_new(marker, metadata)  # completion marker last; never reuse partial caches
    return directory


def verify_prepared(directory, metadata):
    directory = Path(directory)
    for name, digest in metadata["files"].items():
        if Path(name).name != name or sha(directory / name) != digest:
            raise ValueError(f"Prepared cache hash mismatch: {name}")


class Prepared:
    def __init__(self, directory, config, *, allow_test_fixture=False):
        self.directory = Path(directory)
        self.metadata = json.loads((self.directory / "prepared.json").read_text(encoding="utf-8"))
        if self.metadata["dataset"] != "Fashion-MNIST" and not allow_test_fixture:
            raise ValueError("Test fixtures cannot be reported as real data")
        if self.metadata["config"] != config.preparation():
            raise ValueError("Preparation config does not match run")
        self.seed = self.metadata["seed"]
        self.edges = make_graph(config.samples, config.degree, self.seed)
        self.public_ids = np.load(self.directory / 'public_ids.npy', allow_pickle=False)[:config.samples]
        self.private, self.public, self.pseudo, self.test = [], [], [], []
        for client, width in enumerate(config.dimensions):
            load = lambda suffix: np.load(self.directory / f"client_{client}_{suffix}.npy", mmap_mode="r", allow_pickle=False)
            self.private.append(load("private"))
            # The certificate norm and all teacher arithmetic use float64.
            public_mapping = load('public')
            if public_mapping.shape != (config.public_pool, width):
                raise ValueError('Public pool feature shape mismatch')
            self.public.append(np.array(public_mapping[:config.samples], dtype=np.float64))
            public_mapping._mmap.close()
            self.pseudo.append(load("pseudo"))
            self.test.append(load("test"))
            if self.public[-1].shape != (config.samples, width):
                raise ValueError("Public feature shape mismatch")
            if self.private[-1].shape[1] != width or len(self.pseudo[-1]) != len(self.private[-1]):
                raise ValueError("Private feature/pseudolabel shape mismatch")
        self.test_labels = np.load(self.directory / "test_labels.npy", allow_pickle=False)

    def close(self):
        """Release memory mappings explicitly, including on Windows."""
        for array in self.private + self.pseudo + self.test:
            mapping = getattr(array, "_mmap", None)
            if mapping is not None:
                mapping.close()
