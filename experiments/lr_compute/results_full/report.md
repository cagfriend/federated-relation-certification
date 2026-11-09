# P1 LR compute report

LR .05 confirmation inputs; 24 timed runs; 6 standalone memory runs.

## Per-case paired costs

| Case | Family | Seed | Partition | Role | D/B head | D/B saved s | D/B gen | D/B total | D/E head | D/E saved s | D/E gen | D/E total | Traffic equal |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| n12_k10_dirichlet_0.1_seed1001 | n12_k10 | 1001 | dirichlet_0.1 | healthy | 0.6282 | 45.4180 | 0.5014 | 0.6934 | 0.9355 | 5.2933 | 0.9019 | 0.9504 | True |
| n12_k10_dirichlet_0.1_seed1003 | n12_k10 | 1003 | dirichlet_0.1 | known_failure | 0.5766 | 48.2170 | 0.4481 | 0.6619 | 0.8955 | 7.6584 | 0.8486 | 0.9236 | True |
| n12_k10_dirichlet_0.1_seed1101 | n12_k10 | 1101 | dirichlet_0.1 | new_seed | 0.5104 | 59.2619 | 0.3927 | 0.5881 | 0.8203 | 13.5337 | 0.7680 | 0.8622 | True |
| n12_k10_iid_seed1101 | n12_k10 | 1101 | iid | new_seed | 0.5976 | 45.4242 | 0.4603 | 0.6950 | 0.9101 | 6.6634 | 0.8256 | 0.9413 | True |
| n6_k64_dirichlet_0.1_seed1001 | n6_k64 | 1001 | dirichlet_0.1 | healthy | 0.7323 | 42.3901 | 0.6506 | 0.7802 | 0.9643 | 4.2877 | 0.9575 | 0.9724 | True |
| n6_k64_dirichlet_0.1_seed1002 | n6_k64 | 1002 | dirichlet_0.1 | known_failure | 0.7645 | 36.8831 | 0.6766 | NA | 0.9917 | 1.0080 | 0.9774 | NA | True |
| n6_k64_dirichlet_0.1_seed1101 | n6_k64 | 1101 | dirichlet_0.1 | new_seed | 0.7369 | 44.0376 | 0.6494 | 0.7756 | 0.9766 | 2.9560 | 0.9694 | 0.9804 | True |
| n6_k64_iid_seed1101 | n6_k64 | 1101 | iid | new_seed | 0.7217 | 46.6916 | 0.6374 | 0.7623 | 1.0033 | -0.4002 | 0.9833 | 1.0024 | True |

Costs use C0 + additional preparation + shared loading + measured head pipeline. Preparation is reused input work but shown as a comparable reference; timing is exploratory single-process measurement and not a P2 parallel-runtime estimate. K64 seed1002 preparation is marked NA where the recorded historical sleep contamination applies; raw value and reason remain in runs.csv and paired_cost.csv.

## Quality guard

The baseline B final result is evaluated with the predeclared LR-confirmation verdict, including final structure, post-round-20 process guard, and NMI floor. Smoke rows are development only; with 12 rounds the post-round-20 process guard is vacuous and no formal pass claim is made. Per-client checkpoints and final client metrics are reported separately; early phase movement is descriptive and does not replace the final guard.

| Case | Role | Predeclared pass | Final near-99 clients | Mean largest-cluster fraction |
|---|---|---|---:|---:|
| n12_k10_dirichlet_0.1_seed1001 | healthy | True | 0 | 0.3323 |
| n12_k10_dirichlet_0.1_seed1003 | known_failure | True | 0 | 0.3500 |
| n12_k10_dirichlet_0.1_seed1101 | new_seed | True | 0 | 0.3516 |
| n12_k10_iid_seed1101 | new_seed | True | 0 | 0.2970 |
| n6_k64_dirichlet_0.1_seed1001 | healthy | True | 0 | 0.3326 |
| n6_k64_dirichlet_0.1_seed1002 | known_failure | True | 0 | 0.3068 |
| n6_k64_dirichlet_0.1_seed1101 | new_seed | True | 0 | 0.4335 |
| n6_k64_iid_seed1101 | new_seed | True | 0 | 0.3182 |

## Memory scope

Standalone memory results cover only two selected cases and exclude oracle and evaluation work. Peak process memory includes interpreter and input preparation/loading; persistent method arrays are also listed. These limited cases do not support broad memory scaling claims.

All eight full-design case/seed rows are retained independently with role labels; no pooling across seeds or roles. Smoke mode has 12 timed runs and 6 memory runs and exercises the report path only. events.csv contains only flagged client/checkpoint rows; final client metrics are in final_clients.csv. Exact serialized traffic and endpoint counts are reported in runs.csv; traffic equality is checked per paired case.
