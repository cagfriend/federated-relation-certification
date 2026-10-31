# Collaboration mechanism experiment report

**Scope:** This report is exploratory and is not performance confirmation for D/E.
Local uses no public update. The other branches use a fixed public budget. Self and Aggregate may follow different trajectories; their per-round curves are retained as observed.
Case summary timings are diagnostics only and do not support formal performance inferences.

Formal exploratory screening applies only when every case in the partition has `identity.preset == full`; smoke runs validate the path only and cannot determine the screening threshold.

Cases: 9. Partitions: dirichlet_0.1, dirichlet_0.5, iid.

Primary scenario: `dirichlet_0.1`; primary metric: final mean ACC. Preregistered exploratory practical threshold: 0.005 (0.5 percentage points).

The screening label requires exactly three seed-level Aggregate−Self and Aggregate−Shuffled mean-ACC differences, all positive, with each comparison's median at least 0.005. It is a screening label only; new seeds are required for confirmation.

ACC alone determines the screening label. NMI and ARI are secondary paired metrics.

## Paired seed summaries by partition

| Partition | Role | Comparison | Seeds | Median mean-ACC diff | Positive ACC seeds | ACC range | Median worst-ACC diff | Median mean-NMI diff | Positive NMI seeds | Median mean-ARI diff | Positive ARI seeds | Screening |
|---|---|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---|
| dirichlet_0.1 | 主场景 | Aggregate-Self | 3 | 0.0083 | 3 | 0.0082 to 0.0091 | 0.0344 | -0.0062 | 1 | 0.0033 | 3 | 探索筛查门槛未达到 |
| dirichlet_0.1 | 主场景 | Aggregate-Shuffled | 3 | -0.0066 | 0 | -0.0068 to -0.0036 | -0.0111 | 0.0111 | 3 | 0.0035 | 2 | 探索筛查门槛未达到 |
| dirichlet_0.1 | 主场景 | Aggregate-Local | 3 | 0.0032 | 2 | -0.0003 to 0.0045 | 0.0144 | -0.0002 | 1 | 0.0017 | 3 | 次要描述性比较 |
| dirichlet_0.5 | 次要场景 | Aggregate-Self | 3 | 0.0006 | 3 | 0.0003 to 0.0012 | 0.0024 | -0.0006 | 1 | 0.0007 | 3 | 次要描述性比较 |
| dirichlet_0.5 | 次要场景 | Aggregate-Shuffled | 3 | 0.0005 | 3 | 0.0005 to 0.0013 | -0.0005 | 0.0012 | 3 | 0.0011 | 3 | 次要描述性比较 |
| dirichlet_0.5 | 次要场景 | Aggregate-Local | 3 | 0.0008 | 3 | 0.0007 to 0.0010 | 0.0008 | 0.0005 | 2 | 0.0009 | 3 | 次要描述性比较 |
| iid | 次要场景 | Aggregate-Self | 3 | 0.0001 | 2 | -0.0002 to 0.0001 | 0.0001 | -0.0000 | 1 | -0.0000 | 1 | 次要描述性比较 |
| iid | 次要场景 | Aggregate-Shuffled | 3 | 0.0002 | 2 | -0.0004 to 0.0007 | -0.0008 | -0.0001 | 1 | 0.0005 | 3 | 次要描述性比较 |
| iid | 次要场景 | Aggregate-Local | 3 | 0.0003 | 3 | 0.0001 to 0.0003 | 0.0002 | 0.0000 | 2 | 0.0001 | 2 | 次要描述性比较 |

## Evaluation curves

The complete per-round evaluation curves for every supplied case are preserved in `summary.json`; no round or scenario is selected by its best score.
