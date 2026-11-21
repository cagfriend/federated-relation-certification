"""Measure both clocks at the unchanged E43 engine boundaries."""

from functools import partial
import time
from unittest.mock import patch

from experiments.snapshot_certification_timing import engine
from experiments.snapshot_certification_timing.design import require

from ..full_training import worker

PHASES = ('private', 'generation', 'exchange', 'public')
CLOCKS = ('wall', 'cpu')


def stamp():
    return time.perf_counter_ns(), time.process_time_ns()


def duration(start, end):
    return dict(zip(CLOCKS, ((b-a)/1e9 for a, b in zip(start, end, strict=True)), strict=True))


class TrainingProbe:
    def __init__(self):
        self.ticks = []
        self.setup = None
        self.rows = []

    def tick(self):
        # Engine.round already calls its local clock twice per stage.
        instant = stamp()
        self.ticks.append(instant)
        return instant[0]/1e9


class TimedEngine(engine.Engine):
    def __init__(self, *args, probe, **kwargs):
        self.probe = probe
        start = stamp()
        super().__init__(*args, **kwargs)
        probe.setup = duration(start, stamp())

    def round(self, private, public, seed, rnd):
        self.probe.ticks.clear()
        start = stamp()
        stats = super().round(private, public, seed, rnd)
        elapsed = duration(start, stamp())
        ticks = self.probe.ticks
        require(len(ticks) == 2*len(PHASES), 'Unexpected E43 timing boundaries')
        sample = {clock: {'total': elapsed[clock]} for clock in CLOCKS}
        for i, phase in enumerate(PHASES):
            measured = duration(ticks[2*i], ticks[2*i+1])
            for clock in CLOCKS:
                require(measured[clock] >= 0., f'Non-monotone {clock} timing')
                sample[clock][phase] = measured[clock]
            require(abs(measured['wall'] - stats[f'{phase}_seconds']) < 1e-6,
                    f'Phase timing mismatch: {phase}')
        self.probe.rows.append(dict(round=rnd, **sample))
        return stats


def measure(*args, prefix=None):
    probe = TrainingProbe()
    with (
        patch.object(worker, 'Engine', partial(TimedEngine, probe=probe)),
        patch.object(engine, 'perf_counter', probe.tick),
    ):
        reference = worker.run(*args, audit=False, prefix=prefix)
    require(probe.setup is not None and len(probe.rows) == len(reference['timing']), 'Incomplete timing probe')
    # Keep the original worker output, including the observation hashes and power samples.
    return dict(setup=probe.setup, rounds=probe.rows, **reference)
