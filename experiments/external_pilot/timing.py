"""Exclusive CPU wall-clock stage timers; observers never modify tensors."""
from contextlib import contextmanager
import time
from unittest.mock import patch

class Ledger:
    def __init__(self):self.values={};self.stack=[]
    def charge(self,now):
        if self.stack:
            name,start=self.stack[-1];self.values[name]=self.values.get(name,0.)+now-start
            self.stack[-1]=(name,now)
    @contextmanager
    def phase(self,name):
        self.charge(time.perf_counter());self.stack.append((name,time.perf_counter()))
        try:yield
        finally:
            now=time.perf_counter();self.charge(now);self.stack.pop()
            if self.stack:self.stack[-1]=(self.stack[-1][0],time.perf_counter())
    def snapshot(self):return dict(self.values)

def difference(after,before):return {k:after.get(k,0)-before.get(k,0) for k in after.keys()|before.keys()}

@contextmanager
def observe(ledger,wire):
    """Patch only the synchronous worker process, restore even on exceptions."""
    from contextlib import ExitStack
    from . import hetero,flesd
    from experiments.public_scaling import protocol
    def wrapped(fn,name):
        def call(*a,**kw):
            with ledger.phase(name):return fn(*a,**kw)
        return call
    with ExitStack() as stack:
        stack.enter_context(patch.object(wire,'_roundtrip',wrapped(wire._roundtrip,'serialization_seconds')))
        stack.enter_context(patch.object(hetero.Hetero,'_aggregate_kernel',wrapped(hetero.Hetero._aggregate_kernel,'aggregation_seconds')))
        stack.enter_context(patch.object(flesd,'ensemble',wrapped(flesd.ensemble,'aggregation_seconds')))
        for name in ('encode_vector','decode_vector','acknowledgement','check_ack','validate_context'):
            stack.enter_context(patch.object(protocol,name,wrapped(getattr(protocol,name),'serialization_seconds')))
        stack.enter_context(patch.object(protocol.Traffic,'add',wrapped(protocol.Traffic.add,'serialization_seconds')))
        yield
