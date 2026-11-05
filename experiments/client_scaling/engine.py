"""Use the existing audited engine with unchanged K=10 private targets."""
from pathlib import Path
from experiments.k_scaling.engine import run as core_run


def run(directory, spec, method, *, fixture=False, memory=False):
    if spec.config.classes != 10:
        raise ValueError('Client scaling freezes K=10')
    paths = [Path(directory) / f'client_{i}_pseudo.npy'
             for i in range(len(spec.config.dimensions))]
    # K=10 means these are the original targets, not recomputed substitutes.
    # The engine includes its small mapping/validation overhead in loading.
    return core_run(directory, spec, paths, method=method, fixture=fixture,
                    validate=not memory, metrics=not memory, progress=True)
