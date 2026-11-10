# P3 STL-10 fixed-per-client scaling at public LR 0.05

Official STL-10; 54 normal runs; 12 isolated memory runs.

Runs are summarized by regime, N, and partition across seeds. Shared preparation and loading are measured cost references and are not zeroed for reuse. Per-client head is total serial head time divided by N; it is descriptive and not an estimate of parallel delay.

| Regime | N | Partition | Comparison | Seeds | Median head ratio | Range | Wins | Median head saved (s) | Median gen ratio | Median prep+load+head ratio |
|---|---:|---|---|---:|---:|---|---:|---:|---:|---:|
| fixed_per_client | 2 | dirichlet_0.1 | D/B | 3 | 0.6461 | 0.5798–0.7174 | 3/3 | 6.118 | 0.5139 | 0.8484 |
| fixed_per_client | 2 | dirichlet_0.1 | D/E | 3 | 0.8641 | 0.7493–0.9674 | 3/3 | 1.629 | 0.7930 | 0.9490 |
| fixed_per_client | 2 | iid | D/B | 3 | 0.5836 | 0.5301–0.6201 | 3/3 | 6.138 | 0.4413 | 0.8137 |
| fixed_per_client | 2 | iid | D/E | 3 | 0.8872 | 0.8699–0.8883 | 3/3 | 1.341 | 0.8179 | 0.9671 |
| fixed_per_client | 6 | dirichlet_0.1 | D/B | 3 | 0.5643 | 0.5561–0.5991 | 3/3 | 22.470 | 0.4720 | 0.6854 |
| fixed_per_client | 6 | dirichlet_0.1 | D/E | 3 | 0.8856 | 0.7959–0.9065 | 3/3 | 3.635 | 0.8284 | 0.9277 |
| fixed_per_client | 6 | iid | D/B | 3 | 0.5924 | 0.5596–0.6440 | 3/3 | 20.985 | 0.4690 | 0.7315 |
| fixed_per_client | 6 | iid | D/E | 3 | 0.9373 | 0.9057–0.9864 | 3/3 | 1.784 | 0.8854 | 0.9635 |
| fixed_per_client | 12 | dirichlet_0.1 | D/B | 3 | 0.5986 | 0.5045–0.6281 | 3/3 | 38.249 | 0.4974 | 0.7198 |
| fixed_per_client | 12 | dirichlet_0.1 | D/E | 3 | 0.8347 | 0.8145–0.9512 | 3/3 | 11.295 | 0.7909 | 0.8981 |
| fixed_per_client | 12 | iid | D/B | 3 | 0.5809 | 0.5256–0.6019 | 3/3 | 40.040 | 0.4736 | 0.6806 |
| fixed_per_client | 12 | iid | D/E | 3 | 0.8764 | 0.7921–0.8992 | 3/3 | 7.829 | 0.8058 | 0.9136 |

## Final collapse events

A final collapse is any client with one occupied cluster or a largest-cluster fraction ≥0.99 at its final checkpoint. This is an automatic descriptive flag and does not require an ACC gain.

| Regime | N | Partition | Seed | Method | Final collapsed clients |
|---|---:|---|---:|---|---:|
| fixed_per_client | 2 | iid | 1001 | B | 0 |
| fixed_per_client | 2 | iid | 1001 | E | 0 |
| fixed_per_client | 2 | iid | 1001 | D | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1001 | E | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1001 | D | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1001 | B | 0 |
| fixed_per_client | 6 | iid | 1001 | D | 0 |
| fixed_per_client | 6 | iid | 1001 | B | 0 |
| fixed_per_client | 6 | iid | 1001 | E | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1001 | B | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1001 | E | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1001 | D | 0 |
| fixed_per_client | 12 | iid | 1001 | E | 0 |
| fixed_per_client | 12 | iid | 1001 | D | 0 |
| fixed_per_client | 12 | iid | 1001 | B | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1001 | D | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1001 | B | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1001 | E | 0 |
| fixed_per_client | 2 | iid | 1002 | B | 0 |
| fixed_per_client | 2 | iid | 1002 | E | 0 |
| fixed_per_client | 2 | iid | 1002 | D | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1002 | E | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1002 | D | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1002 | B | 0 |
| fixed_per_client | 6 | iid | 1002 | D | 0 |
| fixed_per_client | 6 | iid | 1002 | B | 0 |
| fixed_per_client | 6 | iid | 1002 | E | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1002 | B | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1002 | E | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1002 | D | 0 |
| fixed_per_client | 12 | iid | 1002 | E | 0 |
| fixed_per_client | 12 | iid | 1002 | D | 0 |
| fixed_per_client | 12 | iid | 1002 | B | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1002 | D | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1002 | B | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1002 | E | 0 |
| fixed_per_client | 2 | iid | 1003 | B | 0 |
| fixed_per_client | 2 | iid | 1003 | E | 0 |
| fixed_per_client | 2 | iid | 1003 | D | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1003 | E | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1003 | D | 0 |
| fixed_per_client | 2 | dirichlet_0.1 | 1003 | B | 0 |
| fixed_per_client | 6 | iid | 1003 | D | 0 |
| fixed_per_client | 6 | iid | 1003 | B | 0 |
| fixed_per_client | 6 | iid | 1003 | E | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1003 | B | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1003 | E | 0 |
| fixed_per_client | 6 | dirichlet_0.1 | 1003 | D | 0 |
| fixed_per_client | 12 | iid | 1003 | E | 0 |
| fixed_per_client | 12 | iid | 1003 | D | 0 |
| fixed_per_client | 12 | iid | 1003 | B | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1003 | D | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1003 | B | 0 |
| fixed_per_client | 12 | dirichlet_0.1 | 1003 | E | 0 |

Detailed final per-client metrics are in `final_clients.csv`; all checkpoints are in `client_checkpoints.csv` and `collapse_checkpoints.csv`. `collapse_events.csv` contains only flagged client/checkpoint events. Repeated B/E/D observations are the same quality trajectory, not independent quality evidence.
`runs.csv` includes head phases, exchange, endpoint counts, optimization steps, quality, persistent arrays, serialized traffic, and prep/loading costs. `paired_cost.csv` preserves each seed; `paired_summary.csv` also includes generation and prep-inclusive ranges and win counts. Memory runs are limited to endpoint N and one seed; peak includes interpreter and input verification/loading, with oracle and evaluation disabled.
These are exploratory single measurements per method/configuration. Cross-N changes private splits, representations and trajectories. Serial exchange and serialized bytes do not measure network latency or parallel round time. Any flagged severe final collapse limits claims of useful clustering scalability; costs remain disclosed without selective deletion.

## P3 protocol and quality scope

Private LR 0.1; public effective LR 0.05; public two steps per client per round. Private samples per client: 400. This is a new fixed-per-client experiment, separate from historical fixed-total LR 0.1 results. Cross-N changes data, encoders and trajectories. No ACC improvement requirement.

`quality_guardrails.csv` summarizes the shared B/E/D quality once using B: 0/18 cases have severe final collapse. Flagged costs remain reported; these cases cannot support a claim of healthy clustering at scale. Intermediate concentration is recorded without automatically rejecting a recovered trajectory. No timing exclusions or success thresholds are selected after results.
