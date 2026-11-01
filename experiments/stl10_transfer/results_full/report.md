# STL-10 transfer experiment report

Dataset: **official STL-10**. Runs: 36; preset: full.

Each method was run once per seed, partition and M in an independent serial process. Results are exploratory; this is not a formal independent confirmation and no C1/C2 verdict is made. Paired seed results are summarized by median and range, with win counts.

## Paired timing

| partition | case | comparison | seeds | median head ratio | range | wins | median seconds saved |
|---|---|---:|---:|---:|---:|---:|---:|
| dirichlet_0.1 | m16384_fixed8_privfull | D/B | 3 | 0.6762 | 0.6748–0.7129 | 3/3 | 20.137 |
| dirichlet_0.1 | m16384_fixed8_privfull | D/E | 3 | 0.9582 | 0.8832–1.0318 | 2/3 | 1.882 |
| dirichlet_0.1 | m4096_fixed8_privfull | D/B | 3 | 0.8584 | 0.8518–0.8823 | 3/3 | 5.280 |
| dirichlet_0.1 | m4096_fixed8_privfull | D/E | 3 | 1.0186 | 0.9712–1.0277 | 1/3 | -0.599 |
| iid | m16384_fixed8_privfull | D/B | 3 | 0.6754 | 0.6295–0.7040 | 3/3 | 19.654 |
| iid | m16384_fixed8_privfull | D/E | 3 | 1.0143 | 1.0024–1.0276 | 0/3 | -0.582 |
| iid | m4096_fixed8_privfull | D/B | 3 | 0.8150 | 0.7809–0.8777 | 3/3 | 7.703 |
| iid | m4096_fixed8_privfull | D/E | 3 | 0.9996 | 0.8948–1.0218 | 2/3 | 0.015 |

## Including shared preparation and loading

| partition | case | comparison | median cost ratio | median seconds saved |
|---|---|---|---:|---:|
| dirichlet_0.1 | m16384_fixed8_privfull | D/B | 0.7496 | 20.138 |
| dirichlet_0.1 | m16384_fixed8_privfull | D/E | 0.9703 | 1.885 |
| dirichlet_0.1 | m4096_fixed8_privfull | D/B | 0.9049 | 5.278 |
| dirichlet_0.1 | m4096_fixed8_privfull | D/E | 1.0119 | -0.600 |
| iid | m16384_fixed8_privfull | D/B | 0.7674 | 19.633 |
| iid | m16384_fixed8_privfull | D/E | 1.0094 | -0.556 |
| iid | m4096_fixed8_privfull | D/B | 0.8821 | 7.699 |
| iid | m4096_fixed8_privfull | D/E | 0.9997 | 0.017 |

## Cross-M quality sensitivity

M changes the public graph and target. This comparison is a sensitivity analysis, not a D-specific budget loss. The registered 1 percentage point ACC tolerance is reported per seed; private data, pseudo-labels, initial heads, and public SGD step budget are held fixed across M, while graph targets may differ.

| partition | seed | ACC change, larger M minus smaller M | within −1 pp |
|---|---:|---:|---|
| dirichlet_0.1 | 1001 | -0.0001 | yes |
| dirichlet_0.1 | 1002 | +0.0000 | yes |
| dirichlet_0.1 | 1003 | -0.0000 | yes |
| iid | 1001 | +0.0000 | yes |
| iid | 1002 | +0.0000 | yes |
| iid | 1003 | +0.0000 | yes |

## Per-run diagnostics

Full per-client ACC/NMI/ARI and cluster occupancy are retained in each run JSON under `metrics`; persistent traffic arrays and peak-memory descriptions are retained under each method summary. The C0 preparation and load costs are included in `with_shared_preparation_seconds`; maximum-pool preparation is shared and its original preparation cost is charged to either M. Audit/evaluation time is excluded from the head timer.
