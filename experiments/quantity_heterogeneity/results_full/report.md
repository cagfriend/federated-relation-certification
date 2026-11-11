# STL-10 private quantity heterogeneity, public LR 0.05

Official STL-10; 54 normal runs; 6 isolated memory runs.

Runs are summarized by regime, N, and partition across seeds. Shared preparation and loading are measured cost references and are not zeroed for reuse. Per-client head is total serial head time divided by N; it is descriptive and not an estimate of parallel delay.

| Regime | N | Partition | Comparison | Seeds | Median head ratio | Range | Wins | Median head saved (s) | Median gen ratio | Median prep+load+head ratio |
|---|---:|---|---|---:|---:|---|---:|---:|---:|---:|
| quantity_equal | 6 | dirichlet_0.1 | D/B | 3 | 0.5998 | 0.4775–0.7891 | 3/3 | 24.920 | 0.4680 | 0.7107 |
| quantity_equal | 6 | dirichlet_0.1 | D/E | 3 | 0.8021 | 0.7119–0.9735 | 3/3 | 8.806 | 0.7580 | 0.8618 |
| quantity_equal | 6 | iid | D/B | 3 | 0.5523 | 0.4838–0.6577 | 3/3 | 27.759 | 0.4333 | 0.6749 |
| quantity_equal | 6 | iid | D/E | 3 | 0.8116 | 0.7969–0.8555 | 3/3 | 7.638 | 0.7701 | 0.8842 |
| quantity_moderate | 6 | dirichlet_0.1 | D/B | 3 | 0.5867 | 0.5763–0.6578 | 3/3 | 16.628 | 0.4428 | 0.7191 |
| quantity_moderate | 6 | dirichlet_0.1 | D/E | 3 | 0.9194 | 0.7010–0.9613 | 3/3 | 2.242 | 0.8663 | 0.9532 |
| quantity_moderate | 6 | iid | D/B | 3 | 0.6711 | 0.6350–0.7572 | 3/3 | 19.012 | 0.5275 | 0.7532 |
| quantity_moderate | 6 | iid | D/E | 3 | 0.9582 | 0.9027–1.0854 | 2/3 | 1.377 | 0.8783 | 0.9737 |
| quantity_strong | 6 | dirichlet_0.1 | D/B | 3 | 0.5498 | 0.4575–0.5847 | 3/3 | 26.732 | 0.4018 | 0.6505 |
| quantity_strong | 6 | dirichlet_0.1 | D/E | 3 | 0.9312 | 0.7849–0.9313 | 3/3 | 2.410 | 0.8699 | 0.9544 |
| quantity_strong | 6 | iid | D/B | 3 | 0.5377 | 0.4890–0.6226 | 3/3 | 27.108 | 0.4072 | 0.6403 |
| quantity_strong | 6 | iid | D/E | 3 | 0.8207 | 0.5611–1.0714 | 2/3 | 6.147 | 0.7651 | 0.8842 |

## Final collapse events

A final collapse is any client with one occupied cluster or a largest-cluster fraction ≥0.99 at its final checkpoint. This is an automatic descriptive flag and does not require an ACC gain.

| Regime | N | Partition | Seed | Method | Final collapsed clients |
|---|---:|---|---:|---|---:|
| quantity_equal | 6 | iid | 1001 | B | 0 |
| quantity_equal | 6 | iid | 1001 | E | 0 |
| quantity_equal | 6 | iid | 1001 | D | 0 |
| quantity_moderate | 6 | iid | 1001 | E | **1** |
| quantity_moderate | 6 | iid | 1001 | D | **1** |
| quantity_moderate | 6 | iid | 1001 | B | **1** |
| quantity_strong | 6 | iid | 1001 | D | **2** |
| quantity_strong | 6 | iid | 1001 | B | **2** |
| quantity_strong | 6 | iid | 1001 | E | **2** |
| quantity_equal | 6 | dirichlet_0.1 | 1001 | B | 0 |
| quantity_equal | 6 | dirichlet_0.1 | 1001 | E | 0 |
| quantity_equal | 6 | dirichlet_0.1 | 1001 | D | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1001 | E | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1001 | D | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1001 | B | 0 |
| quantity_strong | 6 | dirichlet_0.1 | 1001 | D | **2** |
| quantity_strong | 6 | dirichlet_0.1 | 1001 | B | **2** |
| quantity_strong | 6 | dirichlet_0.1 | 1001 | E | **2** |
| quantity_equal | 6 | iid | 1002 | B | 0 |
| quantity_equal | 6 | iid | 1002 | E | 0 |
| quantity_equal | 6 | iid | 1002 | D | 0 |
| quantity_moderate | 6 | iid | 1002 | E | 0 |
| quantity_moderate | 6 | iid | 1002 | D | 0 |
| quantity_moderate | 6 | iid | 1002 | B | 0 |
| quantity_strong | 6 | iid | 1002 | D | **2** |
| quantity_strong | 6 | iid | 1002 | B | **2** |
| quantity_strong | 6 | iid | 1002 | E | **2** |
| quantity_equal | 6 | dirichlet_0.1 | 1002 | B | 0 |
| quantity_equal | 6 | dirichlet_0.1 | 1002 | E | 0 |
| quantity_equal | 6 | dirichlet_0.1 | 1002 | D | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1002 | E | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1002 | D | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1002 | B | 0 |
| quantity_strong | 6 | dirichlet_0.1 | 1002 | D | **2** |
| quantity_strong | 6 | dirichlet_0.1 | 1002 | B | **2** |
| quantity_strong | 6 | dirichlet_0.1 | 1002 | E | **2** |
| quantity_equal | 6 | iid | 1003 | B | 0 |
| quantity_equal | 6 | iid | 1003 | E | 0 |
| quantity_equal | 6 | iid | 1003 | D | 0 |
| quantity_moderate | 6 | iid | 1003 | E | **1** |
| quantity_moderate | 6 | iid | 1003 | D | **1** |
| quantity_moderate | 6 | iid | 1003 | B | **1** |
| quantity_strong | 6 | iid | 1003 | D | **2** |
| quantity_strong | 6 | iid | 1003 | B | **2** |
| quantity_strong | 6 | iid | 1003 | E | **2** |
| quantity_equal | 6 | dirichlet_0.1 | 1003 | B | 0 |
| quantity_equal | 6 | dirichlet_0.1 | 1003 | E | 0 |
| quantity_equal | 6 | dirichlet_0.1 | 1003 | D | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1003 | E | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1003 | D | 0 |
| quantity_moderate | 6 | dirichlet_0.1 | 1003 | B | 0 |
| quantity_strong | 6 | dirichlet_0.1 | 1003 | D | **2** |
| quantity_strong | 6 | dirichlet_0.1 | 1003 | B | **2** |
| quantity_strong | 6 | dirichlet_0.1 | 1003 | E | **2** |

Detailed final per-client metrics are in `final_clients.csv`; all checkpoints are in `client_checkpoints.csv` and `collapse_checkpoints.csv`. `collapse_events.csv` contains only flagged client/checkpoint events. Repeated B/E/D observations are the same quality trajectory, not independent quality evidence.
`runs.csv` includes head phases, exchange, endpoint counts, optimization steps, quality, persistent arrays, serialized traffic, and prep/loading costs. `paired_cost.csv` preserves each seed; `paired_summary.csv` also includes generation and prep-inclusive ranges and win counts. Memory runs are limited to endpoint N and one seed; peak includes interpreter and input verification/loading, with oracle and evaluation disabled.
These are exploratory single measurements per method/configuration. Cross-N changes private splits, representations and trajectories. Serial exchange and serialized bytes do not measure network latency or parallel round time. Any flagged severe final collapse limits claims of useful clustering scalability; costs remain disclosed without selective deletion.

## Quantity profiles

N=6 and total private data are fixed. `quantity_equal`, `quantity_moderate` and `quantity_strong` identify separate regimes; do not pool them into one seed estimate. Widths and global private IDs/public IDs are held fixed, but private partitions and encoders change. Private batching uses actual client sizes, so optimizer-step totals can change across profiles.

`private_capacities.csv` reports actual capacity, width, private steps and per-client final quality once using the shared B trajectory. `quality_guardrails.csv` records severe final collapse without requiring ACC improvement. There are 8/18 flagged cases; costs remain disclosed for every case. This is a single measurement per method/configuration, not an independent timing confirmation. No extra communication saving is claimed for identical B/E/D trajectories.
