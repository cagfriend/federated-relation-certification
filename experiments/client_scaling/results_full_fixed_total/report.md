# STL-10 client scaling report

Official STL-10; 54 normal runs; 12 isolated memory runs.

Runs are summarized by regime, N, and partition across seeds. Shared preparation and loading are measured cost references and are not zeroed for reuse. Per-client head is total serial head time divided by N; it is descriptive and not an estimate of parallel delay.

| Regime | N | Partition | Comparison | Seeds | Median head ratio | Range | Wins | Median head saved (s) | Median gen ratio | Median prep+load+head ratio |
|---|---:|---|---|---:|---:|---|---:|---:|---:|---:|
| fixed_total | 2 | dirichlet_0.1 | D/B | 3 | 0.7183 | 0.6943–0.7820 | 3/3 | 5.293 | 0.4594 | 0.8776 |
| fixed_total | 2 | dirichlet_0.1 | D/E | 3 | 0.9195 | 0.8648–1.0043 | 2/3 | 1.181 | 0.7591 | 0.9698 |
| fixed_total | 2 | iid | D/B | 3 | 0.7112 | 0.5552–0.7431 | 3/3 | 5.443 | 0.4399 | 0.8745 |
| fixed_total | 2 | iid | D/E | 3 | 0.9130 | 0.8954–1.0245 | 2/3 | 1.278 | 0.7655 | 0.9671 |
| fixed_total | 6 | dirichlet_0.1 | D/B | 3 | 0.5471 | 0.5167–0.5984 | 3/3 | 22.827 | 0.3865 | 0.6684 |
| fixed_total | 6 | dirichlet_0.1 | D/E | 3 | 0.8775 | 0.6350–0.9054 | 3/3 | 3.647 | 0.7813 | 0.9255 |
| fixed_total | 6 | iid | D/B | 3 | 0.6238 | 0.5841–0.8724 | 3/3 | 16.294 | 0.4449 | 0.7370 |
| fixed_total | 6 | iid | D/E | 3 | 0.8940 | 0.8709–1.3188 | 2/3 | 3.300 | 0.7632 | 0.9333 |
| fixed_total | 12 | dirichlet_0.1 | D/B | 3 | 0.5759 | 0.5135–0.7336 | 3/3 | 36.599 | 0.4361 | 0.6841 |
| fixed_total | 12 | dirichlet_0.1 | D/E | 3 | 1.1009 | 1.0058–1.1648 | 0/3 | -3.963 | 1.0898 | 1.0601 |
| fixed_total | 12 | iid | D/B | 3 | 0.5872 | 0.4810–0.6037 | 3/3 | 34.546 | 0.4635 | 0.6886 |
| fixed_total | 12 | iid | D/E | 3 | 0.8966 | 0.8916–0.9614 | 3/3 | 5.666 | 0.8483 | 0.9295 |

## Final collapse events

A final collapse is any client with one occupied cluster or a largest-cluster fraction ≥0.99 at its final checkpoint. This is an automatic descriptive flag and does not require an ACC gain.

| Regime | N | Partition | Seed | Method | Final collapsed clients |
|---|---:|---|---:|---|---:|
| fixed_total | 2 | iid | 1001 | B | 0 |
| fixed_total | 2 | iid | 1001 | E | 0 |
| fixed_total | 2 | iid | 1001 | D | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1001 | E | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1001 | D | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1001 | B | 0 |
| fixed_total | 6 | iid | 1001 | D | 0 |
| fixed_total | 6 | iid | 1001 | B | 0 |
| fixed_total | 6 | iid | 1001 | E | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1001 | B | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1001 | E | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1001 | D | 0 |
| fixed_total | 12 | iid | 1001 | E | 0 |
| fixed_total | 12 | iid | 1001 | D | 0 |
| fixed_total | 12 | iid | 1001 | B | 0 |
| fixed_total | 12 | dirichlet_0.1 | 1001 | D | 0 |
| fixed_total | 12 | dirichlet_0.1 | 1001 | B | 0 |
| fixed_total | 12 | dirichlet_0.1 | 1001 | E | 0 |
| fixed_total | 2 | iid | 1002 | B | 0 |
| fixed_total | 2 | iid | 1002 | E | 0 |
| fixed_total | 2 | iid | 1002 | D | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1002 | E | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1002 | D | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1002 | B | 0 |
| fixed_total | 6 | iid | 1002 | D | 0 |
| fixed_total | 6 | iid | 1002 | B | 0 |
| fixed_total | 6 | iid | 1002 | E | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1002 | B | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1002 | E | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1002 | D | 0 |
| fixed_total | 12 | iid | 1002 | E | 0 |
| fixed_total | 12 | iid | 1002 | D | 0 |
| fixed_total | 12 | iid | 1002 | B | 0 |
| fixed_total | 12 | dirichlet_0.1 | 1002 | D | 0 |
| fixed_total | 12 | dirichlet_0.1 | 1002 | B | 0 |
| fixed_total | 12 | dirichlet_0.1 | 1002 | E | 0 |
| fixed_total | 2 | iid | 1003 | B | 0 |
| fixed_total | 2 | iid | 1003 | E | 0 |
| fixed_total | 2 | iid | 1003 | D | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1003 | E | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1003 | D | 0 |
| fixed_total | 2 | dirichlet_0.1 | 1003 | B | 0 |
| fixed_total | 6 | iid | 1003 | D | 0 |
| fixed_total | 6 | iid | 1003 | B | 0 |
| fixed_total | 6 | iid | 1003 | E | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1003 | B | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1003 | E | 0 |
| fixed_total | 6 | dirichlet_0.1 | 1003 | D | 0 |
| fixed_total | 12 | iid | 1003 | E | 0 |
| fixed_total | 12 | iid | 1003 | D | 0 |
| fixed_total | 12 | iid | 1003 | B | 0 |
| fixed_total | 12 | dirichlet_0.1 | 1003 | D | **3** |
| fixed_total | 12 | dirichlet_0.1 | 1003 | B | **3** |
| fixed_total | 12 | dirichlet_0.1 | 1003 | E | **3** |

Detailed final per-client metrics are in `final_clients.csv`; all checkpoints are in `client_checkpoints.csv` and `collapse_checkpoints.csv`. `collapse_events.csv` contains only flagged client/checkpoint events. Repeated B/E/D observations are the same quality trajectory, not independent quality evidence.
`runs.csv` includes head phases, exchange, endpoint counts, optimization steps, quality, persistent arrays, serialized traffic, and prep/loading costs. `paired_cost.csv` preserves each seed; `paired_summary.csv` also includes generation and prep-inclusive ranges and win counts. Memory runs are limited to endpoint N and one seed; peak includes interpreter and input verification/loading, with oracle and evaluation disabled.
These are exploratory single measurements per method/configuration. Cross-N changes private splits, representations and trajectories. Serial exchange and serialized bytes do not measure network latency or parallel round time. Any flagged severe final collapse limits claims of useful clustering scalability; costs remain disclosed without selective deletion.
