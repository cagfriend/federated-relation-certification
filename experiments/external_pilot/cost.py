"""Isolated dense-matmul MAC accounting for diagnostic replays.

This deliberately counts dense matrix products only (2 FLOPs per MAC). It is
not an all-operations FLOPs counter: elementwise work, reductions, optimizer
updates, certificate bit/set operations, and library-internal work are out of
scope. Keep it outside timed training runs.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
import math
from typing import Any

import numpy as np


@dataclass
class CostSnapshot:
    macs: int = 0
    calls: int = 0
    active: bool = False

    @property
    def flops(self) -> int:
        return 2 * self.macs

    def as_dict(self) -> dict[str, int | str]:
        return {"metric": "dense_matmul_only", "macs": self.macs,
                "flops": self.flops, "calls": self.calls}


def _macs_matmul(a: Any, b: Any) -> int:
    a_shape, b_shape = tuple(a.shape), tuple(b.shape)
    if len(a_shape) == 1 and len(b_shape) == 1:
        return a_shape[0]
    if len(a_shape) == 1:
        return math.prod(b_shape[:-2]) * a_shape[0] * b_shape[-1]
    if len(b_shape) == 1:
        return math.prod(a_shape[:-2]) * a_shape[-2] * b_shape[0]
    m, k, n = a_shape[-2], a_shape[-1], b_shape[-1]
    batch = np.broadcast_shapes(a_shape[:-2], b_shape[:-2])
    return math.prod(batch) * m * k * n


class _CountedArray(np.ndarray):
    _counter: CostSnapshot | None = None

    def __new__(cls, value: Any, counter: CostSnapshot):
        obj = np.asarray(value).view(cls)
        obj._counter = counter
        return obj

    def __array_finalize__(self, parent):
        self._counter = getattr(parent, "_counter", None)

    def __matmul__(self, other):
        counter = self._counter or getattr(other, "_counter", None)
        if counter is not None and counter.active:
            counter.macs += _macs_matmul(self, other)
            counter.calls += 1
        return super().__matmul__(other)

    def __rmatmul__(self, other):
        counter = self._counter or getattr(other, "_counter", None)
        if counter is not None and counter.active:
            counter.macs += _macs_matmul(other, self)
            counter.calls += 1
        return super().__rmatmul__(other)


def instrument_arrays(value: Any, counter: CostSnapshot) -> Any:
    """Recursively copy arrays into counted subclasses for diagnostic replay."""
    if isinstance(value, np.ndarray):
        return _CountedArray(value, counter)
    if isinstance(value, dict):
        return {k: instrument_arrays(v, counter) for k, v in value.items()}
    if isinstance(value, list):
        return [instrument_arrays(v, counter) for v in value]
    if isinstance(value, tuple):
        return tuple(instrument_arrays(v, counter) for v in value)
    return value


class NumpyMatmulCounter(AbstractContextManager):
    """Count NumPy ``@`` and ``einsum`` in isolated reference replays.

    Pass modules whose local ``np.asarray`` calls would otherwise strip the
    ndarray subclass (e.g. the public_scaling head module). Inputs can be
    recursively converted with :meth:`prepare` before entering the replay.
    """
    def __init__(self, *modules):
        self.snapshot = CostSnapshot()
        self.modules = modules
        self._old = []

    def prepare(self, value: Any) -> Any:
        return instrument_arrays(value, self.snapshot)

    def __enter__(self):
        self.snapshot.active = True
        original_einsum = np.einsum
        self._old.append((np, "einsum", original_einsum))

        def counted_einsum(subscripts, *operands, **kwargs):
            # Dense contraction MACs: output elements times contracted terms.
            if self.snapshot.active and any(isinstance(a,_CountedArray) for a in operands) and isinstance(subscripts, str) and "->" in subscripts:
                lhs, rhs = subscripts.replace(" ", "").split("->")
                terms = lhs.split(",")
                dims = {}
                for term, operand in zip(terms, operands):
                    for label, size in zip(term, operand.shape):
                        dims[label] = size
                contracted = set("".join(terms)) - set(rhs)
                count = math.prod(dims[c] for c in rhs) * math.prod(dims[c] for c in contracted)
                self.snapshot.macs += count
                self.snapshot.calls += 1
            return original_einsum(subscripts, *operands, **kwargs)

        np.einsum = counted_einsum
        for module in self.modules:
            target_np = getattr(module, "np", None)
            if target_np is not None:
                old_asarray = target_np.asarray
                self._old.append((target_np, "asarray", old_asarray))
                target_np.asarray = lambda a, *args, _old=old_asarray, **kwargs: (
                    np.asanyarray(a, *args, **kwargs)
                    if isinstance(a, _CountedArray) else _old(a, *args, **kwargs))
        return self

    def __exit__(self, exc_type, exc, tb):
        for obj, name, value in reversed(self._old):
            setattr(obj, name, value)
        self._old.clear()
        self.snapshot.active = False
        return False


class TorchMatmulCounter(AbstractContextManager):
    """Count executed aten dense matrix products via TorchDispatchMode."""
    OPS = {"aten.mm.default", "aten.bmm.default", "aten.addmm.default",
           "aten.addmv.default", "aten.mv.default", "aten.dot.default"}

    def __init__(self):
        self.snapshot = CostSnapshot()
        self._mode = None

    def __enter__(self):
        from torch.utils._python_dispatch import TorchDispatchMode
        self.snapshot.active = True
        owner = self

        class Mode(TorchDispatchMode):
            def __torch_dispatch__(self, func, types, args=(), kwargs=None):
                kwargs = kwargs or {}
                result = func(*args, **kwargs)
                name = str(func)
                if name in owner.OPS:
                    a, b = args[-2], args[-1]
                    owner.snapshot.macs += _macs_matmul(a, b)
                    owner.snapshot.calls += 1
                return result

        self._mode = Mode()
        self._mode.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            return self._mode.__exit__(exc_type, exc, tb)
        finally:
            self.snapshot.active = False


class CostCounter(AbstractContextManager):
    """Common isolated replay API; snapshot values are numeric for deltas."""
    coverage = {
        "included": "dense matrix multiplication MACs (2 FLOPs per MAC)",
        "excluded": ["NumPy k-means/setup", "elementwise operations and reductions",
                     "optimizer updates", "certificate bitsets/set logic",
                     "non-matmul framework kernels"],
    }

    def __init__(self, *numpy_modules):
        if not numpy_modules:
            from experiments.public_scaling import certification, head
            numpy_modules = (certification, head)
        self._numpy = NumpyMatmulCounter(*numpy_modules)
        self._torch = TorchMatmulCounter()
        self._snapshot = CostSnapshot()

    def prepare(self, algorithm):
        """Convert NumPy arrays in an isolated algorithm/cache object in place."""
        seen = set()

        def visit(obj):
            if isinstance(obj, np.ndarray):
                return _CountedArray(obj, self._snapshot)
            if id(obj) in seen:
                return obj
            seen.add(id(obj))
            if isinstance(obj, dict):
                for key, val in list(obj.items()):
                    obj[key] = visit(val)
            elif isinstance(obj, list):
                obj[:] = [visit(val) for val in obj]
            elif isinstance(obj, tuple):
                return tuple(visit(val) for val in obj)
            elif hasattr(obj, "__dict__") and not obj.__class__.__module__.startswith("torch"):
                for key, val in list(vars(obj).items()):
                    try:
                        setattr(obj, key, visit(val))
                    except (AttributeError, TypeError):
                        pass
            return obj
        return visit(algorithm)

    def snapshot(self) -> dict[str, int]:
        return {"macs": int(self._snapshot.macs), "flops": int(self._snapshot.flops),
                "calls": int(self._snapshot.calls)}

    def __enter__(self):
        self._numpy.snapshot = self._snapshot
        self._torch.snapshot = self._snapshot
        self._snapshot.active = True
        self._numpy.__enter__()
        self._torch.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            self._torch.__exit__(exc_type, exc, tb)
        finally:
            self._numpy.__exit__(exc_type, exc, tb)
            self._snapshot.active = False
        return False
