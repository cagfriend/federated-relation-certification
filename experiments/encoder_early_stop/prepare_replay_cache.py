"""Prepare only the STL-10 caches required by the published replay scripts."""

import argparse
from pathlib import Path

from .run import ROOT

import torch
from threadpoolctl import threadpool_limits

from experiments.external_pilot.design import config
from experiments.external_pilot.prepare import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path,
                        default=ROOT / 'experiments/stl10_transfer/data/stl10_binary')
    parser.add_argument('experiment', choices=('probe', 'selection', 'fallback'))
    args = parser.parse_args()
    source = args.data_dir.resolve()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    package = ROOT / 'experiments/encoder_early_stop'
    folders = {
        'probe': [(1201, ROOT / 'experiments/external_pilot/results_pilot_observed/cache')],
        'selection': [(1204, package / 'results_confirmation/cache/1204')],
        'fallback': [(s, package / 'results_selection_validation/cache' / str(s)) for s in (1207, 1208)],
    }
    with threadpool_limits(1):
        for seed, folder in folders[args.experiment]:
            prepare(folder, source, dict(config('pilot'), seed=seed))
            print(f'Prepared seed {seed}: {folder}', flush=True)


if __name__ == '__main__':
    main()
