from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.special import logsumexp
from threadpoolctl import threadpool_limits

from experiments.private_prior import training
from experiments.private_prior.design import spec
from experiments.public_scaling.head import Head
from experiments.private_workload.sampling import private_workload_epoch


def test_gradient_matches_direct_weighted_softmax_finite_difference():
    rng = np.random.default_rng(12)
    x = rng.normal(size=(9, 3))
    y = np.array([0,0,0,0,0,1,1,2,2])
    cfg = SimpleNamespace(classes=3, private_epochs=1, private_batch=128, head_lr=.1)
    h = Head(3,3,11,0)
    w, b = h.w.copy(), h.b.copy()
    counts = np.bincount(y)
    def objective(ww, bb):
        weighted = x @ ww.T + bb + np.log(counts)
        return np.mean(logsumexp(weighted, axis=1)-weighted[np.arange(len(y)),y])
    loss, n, ids = training.private_workload_epoch(h,x,y,cfg,11,0,1,None)
    assert np.isclose(loss, objective(w,b))
    epsilon = 1e-5
    for array, observed in [(w,(w-h.w)/.1), (b,(b-h.b)/.1)]:
        for index in np.ndindex(array.shape):
            array[index] += epsilon
            plus = objective(w,b)
            array[index] -= 2*epsilon
            minus = objective(w,b)
            array[index] += epsilon
            assert np.isclose(observed[index],(plus-minus)/(2*epsilon), atol=1e-8)
    assert n == len(y) and np.array_equal(ids,np.arange(len(y)))


def test_other_clients_are_bitwise_original_and_invalid_prior_fails():
    cfg = spec("smoke").config
    rng = np.random.default_rng(21)
    for c in (1,2,4,5):
        h, ref = Head(3,10,1,c), Head(3,10,1,c)
        x, y = rng.normal(size=(20,3)), np.arange(20)%10
        a = training.private_workload_epoch(h,x,y,cfg,1,c,2,None)
        b = private_workload_epoch(ref,x,y,cfg,1,c,2,None)
        assert np.array_equal(h.w,ref.w) and np.array_equal(h.b,ref.b)
        assert a[:2] == b[:2] and np.array_equal(a[2],b[2])
    with pytest.raises(ValueError):
        training.log_prior(np.array([0,1]),10)


def test_engine_snapshot_has_only_declared_import_changes():
    root = Path(__file__).resolve().parents[2]
    original = (root/"experiments/local_public_lr/engine.py").read_text()
    changed = (root/"experiments/private_prior/engine.py").read_text()
    assert original[original.index("import hashlib"):] == changed[changed.index("import hashlib"):].replace(
        "from experiments.private_workload.sampling import subset_digest\nfrom .training import private_workload_epoch",
        "from experiments.private_workload.sampling import private_workload_epoch, subset_digest").replace(
        "from experiments.local_public_lr import probes","from . import probes").replace(
        "from experiments.local_public_lr.design import BRANCHES, PROBE_SIZES, public_client_weights",
        "from .design import BRANCHES, PROBE_SIZES, public_client_weights")


def test_correction_is_private_and_does_not_leak_into_teacher_or_public():
    from experiments.private_prior import engine
    from experiments.private_prior.fixture import prepare
    from experiments.public_scaling.head import ce_loss_grad
    import tempfile
    cfg = spec("smoke")
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as tmp:
        directory = prepare(Path(tmp)/"cache",Path(tmp)/"source",cfg,1001,"iid")
        with threadpool_limits(limits=1):
            record = engine.run(directory,cfg,branch="local_lr",fixture=True,progress=False)
        # Independently build the whole first round, using raw logits for all forwards.
        from experiments.public_scaling.head import relation_loss_grad, private_epoch
        from experiments.public_budget.student import selected_edges
        from experiments.public_scaling.graphs import make_graph
        from experiments.local_public_lr.design import public_client_weights
        from experiments.local_public_lr.engine import _head_digest
        heads = [Head(d,10,1001,c) for c,d in enumerate(cfg.config.dimensions)]
        graph = make_graph(cfg.config.samples,cfg.config.degree,1001)
        features = [np.load(directory/f"client_{c}_public.npy")[:cfg.config.samples].astype(np.float64) for c in range(6)]
        relations = []
        for c,h in enumerate(heads):
            x = np.load(directory/f"client_{c}_private.npy").astype(np.float64)
            y = np.load(directory/f"client_{c}_pseudo.npy")
            if c in (0,3):
                ids = np.random.default_rng(np.random.SeedSequence([1001,401,c,1,0])).permutation(len(y))
                prior = np.log(np.bincount(y,minlength=10)/len(y))
                _,dw,db = ce_loss_grad(x[ids],y[ids],h.w,h.b+prior)
                h.apply(dw,db,.1)
            else:
                private_epoch(h,x,y,cfg.config,1001,c,1)
            assert _head_digest(h) == record["diagnostic_records"][0]["clients"][c]["T1"]["head_digest"]
            labels = (features[c]@h.w.T+h.b).argmax(axis=1)
            relations.append((labels[graph[:,0]] == labels[graph[:,1]]).astype(float))
        targets = np.mean(relations,axis=0)
        for c,h in enumerate(heads):
            order = selected_edges(cfg,1001,c,1)
            for start in range(0,len(order),cfg.config.public_edge_batch):
                ids = order[start:start+cfg.config.public_edge_batch]
                vertices,inverse = np.unique(graph[ids],return_inverse=True)
                _,dw,db = relation_loss_grad(features[c][vertices],inverse.reshape(-1,2),targets[ids],h.w,h.b)
                h.apply(dw,db,cfg.config.head_lr*public_client_weights("local_lr")[c])
            assert _head_digest(h) == record["diagnostic_records"][0]["clients"][c]["T2"]["head_digest"]
