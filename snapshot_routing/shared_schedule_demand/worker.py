"""Run all paths through the same training and original E54 audit windows."""

from contextlib import contextmanager
from functools import partial
from unittest.mock import patch

from experiments.private_corrected_guard.run import digest
from experiments.snapshot_certification_timing.design import require
from ..full_training import worker as full_worker
from ..on_demand import engine, worker as demand_worker
from .protocol import Schedule, SharedScheduleProtocol

EXPLICIT = 'Demand'
SHARED = 'SharedDemand'
METHODS = ('D', EXPLICIT, SHARED)


@contextmanager
def shared_engine(cfg, ref, audit_rows):
    # Use the actual public IDs loaded by the unchanged training worker.
    public_digest = None
    original_load = demand_worker.load_bank

    def load(*args, **kwargs):
        nonlocal public_digest
        public, ids = original_load(*args, **kwargs)
        public_digest = digest(ids.numpy())
        require(public_digest == ref['public_ids_digest'], 'Wrong local public sample order')
        return public, ids

    def construct(*args, **kwargs):
        schedule = Schedule(cfg['seed'], cfg['public_size'], 1, cfg['public_steps'],
                            cfg['relation_batch'], len(cfg['widths']), public_digest)
        factory = partial(SharedScheduleProtocol, schedule=schedule, audit_rows=audit_rows)
        with patch.object(engine, 'DemandProtocol', factory):
            return engine.DemandEngine(*args, **kwargs)

    with patch.object(demand_worker, 'load_bank', load), patch.object(demand_worker, 'DemandEngine', construct):
        yield


def run(source, ref, base, prep, bank, method, baseline, *, audit):
    if method in ('B', 'D'):
        return full_worker.run(source, ref, base, prep, bank, method, audit=audit)
    if method == EXPLICIT:
        return demand_worker.run(source, ref, base, prep, bank, baseline, audit=audit)
    require(method == SHARED, 'Unknown method')
    rows = [] if audit else None
    with shared_engine(ref['cfg'], ref, rows):
        result = demand_worker.run(source, ref, base, prep, bank, baseline, audit=audit)
    return dict(**result, schedule_diagnostics=rows or [])


def shared_accounting(explicit, shared):
    """Disentangle gross removed traffic, registration, and the actual net effect."""
    e = explicit['traffic_breakdown']
    s = shared['traffic_breakdown']
    request, union = e['request_up_bytes'], e['union_down_bytes']
    require({key: value for key, value in e.items() if key not in ('request_up_bytes', 'union_down_bytes')} == s,
            'Shared schedule changed round payload bytes')
    first, second = explicit['setup_traffic'], shared['setup_traffic']
    register_up = second['up_bytes'] - first['up_bytes']
    register_down = second['down_bytes'] - first['down_bytes']
    require(register_up > 0 and register_down > 0, 'Schedule registration bytes missing')
    expected_up, expected_down = request-register_up, union-register_down
    a, b = explicit['traffic'], shared['traffic']
    require(a['up_bytes'] - b['up_bytes'] == expected_up and a['down_bytes'] - b['down_bytes'] == expected_down
            and a['total_bytes'] - b['total_bytes'] == expected_up+expected_down, 'Traffic accounts do not balance')
    require(second['messages'] - first['messages'] == first['messages']
            and a['messages'] - b['messages'] == first['messages']*(len(explicit['scope'])-1),
            'Unexpected registration or per-round message count')
    return dict(request_up_removed=request, union_down_removed=union,
                schedule_setup_up=register_up, schedule_setup_down=register_down,
                net_up_saved=expected_up, net_down_saved=expected_down, net_total_saved=expected_up+expected_down,
                net_messages_saved=a['messages']-b['messages'])
