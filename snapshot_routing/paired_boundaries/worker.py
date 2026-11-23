"""Reuse the full and Demand training paths with the same-bound E control."""

from contextlib import nullcontext
from unittest.mock import patch

import numpy as np

from experiments.public_scaling.endpoint_bias import EndpointBiasGenerator
from experiments.snapshot_certification_timing import engine
from experiments.snapshot_certification_timing.design import require
from ..full_training import worker as full_worker
from ..on_demand import worker as demand_worker


def run(source, ref, cfg, prep, bank, method, baseline, *, audit):
    if method == 'Demand':
        work, args, cls = demand_worker.run, (baseline,), demand_worker.DemandEngine
    else:
        work, args, cls = full_worker.run, (method,), engine.Engine

    def execute():
        return work(source, ref, cfg, prep, bank, *args, audit=audit)

    if method == 'E':
        def point(features, weights, bias, edges, mode):
            require(mode == 'point', 'Same-bound E must use the point path')
            return EndpointBiasGenerator(features, weights, bias, edges, mode=mode)
        factory = patch.object(engine, 'make_generator', point)
    else:
        factory = nullcontext()

    with factory:
        if not audit:
            return execute()
        use = np.zeros(len(cfg['widths']), dtype=np.int64)
        original = cls.round

        def observe(self, *round_args):
            out = original(self, *round_args)
            use[:] += out['endpoints']
            return out

        with patch.object(cls, 'round', observe):
            result = execute()
    result['client_endpoints'] = use.tolist()
    return result
