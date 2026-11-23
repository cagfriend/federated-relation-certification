"""Freeze the Fashion-MNIST transfer workload and timing order."""

from experiments.public_scaling.config import Config

SEEDS = (3101, 3102, 3103)
PARTITIONS = ('iid', 'dirichlet_0.1')
METHODS = 'BED'
ORDERS = (('BED', 'EDB', 'DBE'), ('DEB', 'BDE', 'EBD'))
PUBLIC_WEIGHTS = (.125, .5, .5, .125, .5, .5)
PUBLIC_STEPS = 2
GUARD = .5
HEAD_THRESHOLD = 3.


def configuration(preset):
    full = preset == 'full'
    samples = 4096 if full else 128
    private_per_client = 200 if full else 60
    return Config(dimensions=(128, 128, 128, 256, 256, 256) if full else (32, 32, 32, 64, 64, 64),
                  public_pool=samples, samples=samples, train_limit=samples+6*private_per_client,
                  test_limit=1000 if full else 128, rounds=200 if full else 3,
                  eval_every=10 if full else 1, prepare_threads=1, pretrain_batch=64,
                  pretrain_epochs=5 if full else 1, kmeans_restarts=3,
                  public_edge_batch=64 if full else 16)


def design(preset):
    cases = [dict(seed=seed, partition=part) for seed in (SEEDS if preset == 'full' else SEEDS[:1])
             for part in PARTITIONS]
    reps = 3 if preset == 'full' else 1
    blocks = []
    for r in range(reps):
        for j in range(len(cases)):
            i = (j+r) % len(cases)
            blocks.append(dict(case=cases[i], repeat=r+1, order=ORDERS[(i+i//2) % 2][r]))
    return cases, blocks


def cell_id(case):
    return f"{case['seed']}_{case['partition']}"
