"""Exact-capacity STL-10 partitions for quantity heterogeneity.

Non-uniform modes retain the old Dirichlet client/class affinity idea, but
integerize against explicit client capacities; their class-allocation path is
therefore not the historical equal-capacity trajectory.
"""
import hashlib
import numpy as np


def partition_indices(labels, public_pool, clients, seed, partition, capacities=None):
    y = np.asarray(labels)
    if y.ndim != 1 or not len(y) or not np.issubdtype(y.dtype, np.integer) or np.any((y < 0) | (y > 9)):
        raise ValueError("labels must be a nonempty vector in [0,9]")
    if type(clients) is not int or clients < 1 or type(public_pool) is not int or not 0 <= public_pool < len(y):
        raise ValueError("clients/public_pool are invalid")
    if partition not in ("iid", "dirichlet_0.1"):
        raise ValueError(f"Unsupported partition {partition!r}")
    if capacities is None:
        count = len(y) - public_pool
        capacities = [count // clients + (i < count % clients) for i in range(clients)]
    raw_capacities = np.asarray(capacities)
    if raw_capacities.ndim != 1 or not np.issubdtype(raw_capacities.dtype, np.integer):
        raise ValueError("capacities must be integers")
    capacities = raw_capacities.astype(np.int64, copy=False)
    if len(capacities) != clients or np.any(capacities < 10) or capacities.sum() != len(y)-public_pool:
        raise ValueError("capacities must be >=10 and sum to the private dataset size")
    # Keep the equal-capacity legacy trajectory exactly intact for P3 reuse.
    if len(set(capacities.tolist())) == 1:
        from experiments.noniid_clustering.data import partition_indices as legacy
        return legacy(y, public_pool, clients, int(seed), partition)
    rng = np.random.default_rng(np.random.SeedSequence([int(seed), 210]))
    order = rng.permutation(len(y)); public = order[:public_pool].astype(np.int64)
    universe = order[public_pool:].astype(np.int64)
    private_y = y[universe].astype(np.int64)
    totals = np.bincount(private_y, minlength=10).astype(np.int64)
    result = [np.empty(int(c), dtype=np.int64) for c in capacities]; offsets=np.zeros(clients,dtype=int)
    if partition == "iid":
        result = [np.asarray(x, dtype=np.int64) for x in np.split(universe, np.cumsum(capacities)[:-1])]
    else:
        from experiments.noniid_clustering.data import _ipf, _integerize
        affinity = rng.dirichlet(np.full(10, .1, dtype=np.float64), size=clients)
        fitted = _ipf(affinity, capacities, totals)
        allocation = _integerize(fitted, capacities, totals)
        for cls in range(10):
            ids=universe[private_y==cls].copy(); rng.shuffle(ids); pos=0
            for i in range(clients):
                count=int(allocation[i,cls]); result[i][offsets[i]:offsets[i]+count]=ids[pos:pos+count]; offsets[i]+=count; pos+=count
            if pos != len(ids): raise RuntimeError("class allocation did not consume all IDs")
        if not np.array_equal(offsets, capacities): raise RuntimeError("capacity allocation did not fill clients")
    if partition != "iid":
        for ids in result: rng.shuffle(ids)
    joined=np.concatenate([public,*result])
    if not np.array_equal(np.asarray([len(a) for a in result]), capacities) or len(joined)!=len(y) or len(np.unique(joined))!=len(y):
        raise RuntimeError("quantity partition failed exact capacity/coverage audit")
    hist=[np.bincount(y[a],minlength=10).astype(int).tolist() for a in result]
    diag={"partition":partition,"alpha":None if partition=="iid" else .1,"public_count":int(len(public)),
          "private_count":int(sum(capacities)),"client_counts":capacities.astype(int).tolist(),
          "target_capacities":capacities.astype(int).tolist(),"client_class_histograms":hist,
          "private_class_totals":np.sum(hist,axis=0).astype(int).tolist(),
          "partition_algorithm":"quantity-capacity-iid-permutation" if partition=="iid" else "quantity-capacity-ipf-residual-flow-v1",
          "indices_sha256":hashlib.sha256(np.concatenate([public,*result]).astype('<i8').tobytes()).hexdigest()}
    return public, result, diag
