from collections import Counter

from experiments.snapshot_certification_timing.design import FORMAL, TRIPLES, cfg_for, require

SIZES = {'full': (512, 4096, 16384), 'smoke': (32, 64, 128)}


def schedule(preset):
    """Balance method positions per cell and rotate the order of sizes."""
    contexts = FORMAL if preset == 'full' else FORMAL[:1]
    sizes = SIZES[preset]
    result = []
    for stage in ('audit', 'timing'):
        for i, (seed, part) in enumerate(contexts):
            repeats = 3 if stage == 'timing' and preset == 'full' else 1
            for repeat in range(repeats):
                for j in range(len(sizes)):
                    offset = (i+repeat) % len(sizes)
                    m = sizes[(offset+j) % len(sizes)]
                    k = sizes.index(m)
                    methods = TRIPLES[(i+k) % 2][repeat] if stage == 'timing' and preset == 'full' else 'BED'
                    for method in methods:
                        result.append(dict(seed=seed, partition=part, public_size=m, stage=stage,
                                           repeat=repeat+1, method=method))
    paths = [run_path(c) for c in result]
    require(len(paths) == len(set(paths)), 'Duplicate schedule entry')
    require(Counter(c['stage'] for c in result) == ({'audit':36, 'timing':108} if preset == 'full'
                                                   else {'audit':9, 'timing':9}), 'Invalid schedule')
    return result


def context_id(case):
    return f"{case['seed']}_{case['partition']}"


def cell_id(case):
    return f"{context_id(case)}_m{case['public_size']}"


def run_path(case):
    return f"{case['stage']}/{cell_id(case)}_{case['method']}_r{case['repeat']}.json"


def configs(preset, case):
    base = cfg_for(preset, case['seed'])
    return base, dict(base, public_size=case['public_size'])
