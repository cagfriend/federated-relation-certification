"""Verified preparation reuse for the B-only public learning-rate study."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np

from experiments.stl10_transfer import data as transfer_data
from experiments.k_scaling import data as k_data


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _historical(root, case, spec, fixture):
    if fixture:
        return None
    base = Path(__file__).resolve().parents[1]
    seed, part, family = int(case["seed"]), case["partition"], case["family"]
    marker = None
    if family == "n12_k10" and seed in (1001, 1003):
        marker = base / "client_scaling/results_full_fixed_total/inputs" / f"{seed}_{part}_fixed_total_12.json"
    elif family == "n6_k64" and seed in (1001, 1002):
        marker = base / "stl10_transfer/results_full" / f"prepared_{part}_seed_{seed}.json"
    if marker is None or not marker.is_file():
        return None
    ref = json.loads(marker.read_text(encoding="utf-8"))
    if family == "n12_k10":
        path = Path(ref["path"])
        digest = ref["metadata_sha256"]
    else:
        path = Path(ref["path"])
        digest = ref["metadata_sha256"]
    metadata = path / "prepared.json"
    if not metadata.is_file() or _sha(metadata) != digest:
        raise ValueError(f"Historical preparation marker mismatch: {marker}")
    cfg = replace(spec.config, classes=10)
    transfer_data.verify(path, cfg, seed, part, fixture=False)
    return path


def _resolve(root, case, spec, fixture=False):
    spec.validate()
    cfg = spec.config
    family = case["family"]
    if family not in ("n12_k10", "n6_k64"):
        raise ValueError("Unknown public-LR family")
    expected_n = 2 if fixture else (12 if family == "n12_k10" else 6)
    if len(cfg.dimensions) != expected_n or cfg.classes != (10 if family == "n12_k10" else 64):
        raise ValueError("Case family does not match actual N/K")
    seed, part = int(case["seed"]), case["partition"]
    base = _historical(root, case, spec, fixture)
    if base is None:
        if not fixture and seed != 1101:
            raise FileNotFoundError(f"No verified historical base for seed={seed}, partition={part}")
        print(f"[public-lr data] preparing base seed={seed} partition={part}", flush=True)
        data_dir = Path(root) / 'fixture_data' if fixture else Path(__file__).resolve().parents[1] / 'stl10_transfer/data'
        base = transfer_data.prepare(Path(root) / ("fixture_prepared" if fixture else "prepared"), data_dir,
                                     replace(cfg, classes=10), seed, part, download=False, fixture=fixture)
    transfer_data.verify(base, replace(cfg, classes=10), seed, part, fixture=fixture)
    kdir = None
    if cfg.classes == 64:
        env_path = Path(__file__).resolve().parents[1] / "k_scaling/results_full/environment.json"
        key = f"{seed}|{part}|64"
        if not fixture and env_path.is_file():
            env = json.loads(env_path.read_text(encoding="utf-8"))
            hist = env.get("inputs", {}).get(key)
            if hist is not None:
                if Path(hist["base"]).resolve() != base.resolve() or hist.get("metadata_sha256") != _sha(Path(hist["pseudo"]) / "prepared_k.json"):
                    raise ValueError("Historical K=64 environment does not match selected base or pseudo metadata")
                kdir = Path(hist["pseudo"])
                k_data.verify(kdir, base, spec, fixture=False)
        if kdir is None:
            kdir = k_data.prepare(base, spec, Path(root) / "prepared_k", fixture=fixture)
    return Path(base), Path(kdir) if kdir else None


def prepare_input(root, case, spec, fixture=False) -> dict:
    base, kdir = _resolve(root, case, spec, fixture)
    entry = {"base_directory": str(base.resolve()), "base_metadata_sha256": _sha(base / "prepared.json"),
             "seed": int(case["seed"]), "partition": case["partition"], "family": case["family"],
             "fixture": bool(fixture)}
    if kdir:
        entry.update(k_directory=str(kdir.resolve()), k_metadata_sha256=_sha(kdir / "prepared_k.json"))
    verify_input(entry, spec, fixture)
    print(f"[public-lr data] ready {case['family']} seed={case['seed']} partition={case['partition']}", flush=True)
    return entry


def verify_input(entry, spec, fixture=False) -> None:
    cfg = spec.config
    base = Path(entry["base_directory"])
    if entry.get("fixture") is not bool(fixture) or _sha(base / "prepared.json") != entry.get("base_metadata_sha256"):
        raise ValueError("Base preparation digest/fixture mismatch")
    transfer_data.verify(base, replace(cfg, classes=10), int(entry["seed"]), entry["partition"], fixture=fixture)
    if cfg.classes == 64:
        kd = Path(entry["k_directory"])
        if _sha(kd / "prepared_k.json") != entry.get("k_metadata_sha256"):
            raise ValueError("K preparation digest mismatch")
        k_data.verify(kd, base, spec, fixture=fixture)
        paths = k_data.pseudo_paths(kd)
        if len(paths) != len(cfg.dimensions) or any(not p.is_file() for p in paths):
            raise ValueError("K-specific pseudo-label assets missing")


def load_input(entry, spec, fixture=False):
    verify_input(entry, spec, fixture)
    from experiments.public_scaling.data import Prepared
    base = Path(entry["base_directory"])
    cfg = replace(spec.config, classes=10)
    data = Prepared(base, cfg, allow_test_fixture=True)
    mappings = []
    try:
        paths = (k_data.pseudo_paths(entry["k_directory"]) if spec.config.classes == 64
                 else [base / f"client_{i}_pseudo.npy" for i in range(len(cfg.dimensions))])
        for i, path in enumerate(paths):
            arr = np.load(path, mmap_mode="r", allow_pickle=False)
            if arr.shape != data.pseudo[i].shape or arr.dtype.kind not in "iu" or np.any(arr < 0) or np.any(arr >= spec.config.classes):
                mm = getattr(arr, "_mmap", None)
                if mm is not None: mm.close()
                raise ValueError(f"Invalid pseudo-label mapping for client {i}")
            mappings.append(arr)
        for old in data.pseudo:
            mm = getattr(old, "_mmap", None)
            if mm is not None: mm.close()
        data.pseudo = mappings
        return data
    except Exception:
        for arr in mappings:
            mm = getattr(arr, "_mmap", None)
            if mm is not None: mm.close()
        data.close()
        raise
