# Low-capacity stability diagnostic report

Official STL-10 diagnostic; 12 runs. No performance conclusions.

|Case|Branch|Rounds|Recovery check|
|---|---|---:|---|
|strong_iid_seed1001|baseline|40|short_replay_only|
|strong_dirichlet_0.1_seed1001|baseline|40|short_replay_only|
|strong_iid_seed1002|baseline|40|short_replay_only|
|strong_dirichlet_0.1_seed1002|baseline|40|short_replay_only|
|strong_iid_seed1001|private_only|200|released_severe_collapse|
|strong_dirichlet_0.1_seed1001|private_only|200|released_severe_collapse|
|strong_iid_seed1002|private_only|200|released_severe_collapse|
|strong_dirichlet_0.1_seed1002|private_only|200|released_severe_collapse|
|strong_iid_seed1001|low_lr|200|released_severe_collapse|
|strong_dirichlet_0.1_seed1001|low_lr|200|released_severe_collapse|
|strong_iid_seed1002|low_lr|200|released_severe_collapse|
|strong_dirichlet_0.1_seed1002|low_lr|200|released_severe_collapse|

## Interpretation

Baseline is a short exact replay and does not supply unrecorded historical T0/T1/T2 data at rounds 160/180/200. Those historical fields are NA. Existing historical test metrics are retained separately.
T0 precedes private SGD, T1 follows private SGD and is the actual teacher snapshot, T2 follows public SGD. Private-only runs no public gradient/update; its T2 equals T1. Probe snapshots and independent RNG stream must not affect training.
Every specified checkpoint and all six clients must pass: at least two occupied clusters and largest fraction below 0.99. Passing means release of severe collapse only; no ACC gain or new NMI threshold. Full process events remain in stage/test logs.
All-client lower public LR changes both local steps and future teacher feedback. Outcomes cannot identify one unique cause. Diagnostic timing includes instrumentation effects and must not be pooled with historical certification benchmarks.
