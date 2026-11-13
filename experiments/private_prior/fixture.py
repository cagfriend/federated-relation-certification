"""Explicit synthetic feature fixture; it never supplies formal measurements."""
from pathlib import Path

import numpy as np

from experiments.quantity_heterogeneity import data
from experiments.stl10_transfer.run import digest, write_new


def prepare(cache, source, spec, seed, partition):
    import json
    directory = data.prepare(cache, source, spec, seed, partition, profile="strong", fixture=True)
    metadata = json.loads((directory/"prepared.json").read_bytes())
    if metadata.get("private_prior_synthetic_features") == 1:
        return directory
    if metadata["dataset"] != "STL-10 fixture":
        raise ValueError("Synthetic replacement requires an explicit fixture cache")
    # The tiny AE fixture can yield identical zero features. Here every pseudo
    # cluster is represented so the registered correction can be exercised.
    for c, record in enumerate(metadata["clients"]):
        rng = np.random.default_rng(np.random.SeedSequence([seed, 8761, c]))
        width, count = record["width"], record["private_samples"]
        centers = rng.normal(scale=.3, size=(10,width))
        pseudo = np.arange(count,dtype=np.int64)%10
        arrays = {"pseudo": pseudo, "centers": centers,
                  "private": centers[pseudo]+rng.normal(scale=.05,size=(count,width))}
        for domain,n in (("public",spec.config.public_pool),("test",spec.config.test_limit)):
            labels = np.arange(n)%10
            arrays[domain] = centers[labels]+rng.normal(scale=.05,size=(n,width))
        for suffix, array in arrays.items():
            path = directory/f"client_{c}_{suffix}.npy"
            np.save(path,array)
            metadata["files"][path.name] = digest(path)
        record["pseudo_histogram"] = np.bincount(pseudo,minlength=10).tolist()
    metadata["private_prior_synthetic_features"] = 1
    write_new(directory/"prepared.json",metadata)
    data.verify(directory,spec.config,seed,partition,profile="strong",fixture=True)
    return directory
