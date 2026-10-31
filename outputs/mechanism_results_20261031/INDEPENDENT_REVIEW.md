# Independent results review — collaboration mechanism

Date: 2026-10-31  
Scope: read-only audit of `experiments/collaboration_mechanism/results_full`. No training, source edits, or raw-result edits were performed. Quality effects below were recomputed independently from the per-client final metrics in `final_clients.csv`; repeated clients, rounds, and probe rows were not treated as independent seeds.

## Completion and integrity

- `completed.json` declares 9 cases, 36 training trajectories, 5,400 replay-checked target records, 7,128 gradient-probe rows, 3,600 historical Local/B round-method matches, and zero mismatches. All nine expected `(partition, seed)` JSON cases are present (three partitions × seeds 404/505/606); the formerly missing `dirichlet_0.1_seed_606.json` is present.
- The completion manifest lists 26 output files. I independently found the same 26 files and recomputed SHA-256 for every listed file: no missing, extra, or hash-mismatched outputs.
- Every case JSON passed payload validation. The frozen collaboration-mechanism source hashes in `environment.json` match the current source files. For all nine cases, I reconstructed each Self/Aggregate/Shuffled relation target from its packed rows and replayed the recorded digests and derived diagnostics; all 5,400 records matched. I also compared each case against its historical reference: all 400 Local/B round-method pairs per case matched, including evaluation records, with no mismatch (3,600 total).
- Completion status is therefore **complete for the declared 9-case run**, with output-manifest integrity verified. The existing `completed.json` is treated as the run’s completion record; this review did not independently reproduce the full training.

## Protocol and comparison fairness

Source inspection and the logged identities support a matched-target comparison: each of four branches starts from the same initial-head digest within a case and has equal private-training budgets. Self, Aggregate, and Shuffled receive the same public-update budget; Local receives no public update. Target generation follows the post-private snapshot. Aggregate uses the average of the clients’ relation rows; Shuffled applies the same seeded edge permutation to that aggregate vector, preserving its value multiset while changing edge assignment. Public truth is logged for offline target diagnostics. Probe rows record shared student-snapshot and batch digests across counterfactual targets; they are diagnostics, not training updates. Historical Local and B are mapped to Local and Aggregate for exact round/evaluation replay.

Aggregate-versus-Shuffled is the closest outcome comparison for the value of edge assignment, but it does not isolate that mechanism in these independently evolving branches. Each branch constructs targets from its own current post-private relations, so its raw aggregate vector, multiset, and subsequent trajectory can differ. Only in a same-anchor counterfactual probe—where snapshot and batches are held fixed—do Aggregate and Shuffled necessarily share the same target-value multiset and differ only by edge assignment. Aggregate-versus-Self also changes target distribution and cross-client mixing.

## Independent final-quality recomputation

I averaged each method’s six client final scores within each seed, then calculated paired method differences per seed. The table shows the seed differences and their median. These are three paired seeds per partition, not 18 independent client observations.

| Partition | Comparison | Mean ACC differences by seed (404, 505, 606) | Median ACC | ACC-positive seeds | Median NMI | Median ARI |
|---|---|---:|---:|---:|---:|---:|
| Dirichlet 0.1 | Aggregate − Self | +0.00833, +0.00817, +0.00912 | +0.00833 | 3/3 | −0.00619 | +0.00328 |
| Dirichlet 0.1 | Aggregate − Shuffled | −0.00362, −0.00682, −0.00662 | −0.00662 | 0/3 | +0.01110 | +0.00353 |
| Dirichlet 0.1 | Aggregate − Local | +0.00317, −0.00028, +0.00445 | +0.00317 | 2/3 | −0.00024 | +0.00174 |
| Dirichlet 0.5 | Aggregate − Self | +0.00117, +0.00028, +0.00057 | +0.00057 | 3/3 | −0.00065 | +0.00070 |
| Dirichlet 0.5 | Aggregate − Shuffled | +0.00050, +0.00125, +0.00048 | +0.00050 | 3/3 | +0.00121 | +0.00110 |
| Dirichlet 0.5 | Aggregate − Local | +0.00080, +0.00097, +0.00068 | +0.00080 | 3/3 | +0.00050 | +0.00087 |
| IID | Aggregate − Self | +0.00008, −0.00020, +0.00007 | +0.00007 | 2/3 | −0.000003 | −0.000035 |
| IID | Aggregate − Shuffled | +0.00017, −0.00035, +0.00068 | +0.00017 | 2/3 | −0.00011 | +0.00051 |
| IID | Aggregate − Local | +0.00030, +0.00005, +0.00033 | +0.00030 | 3/3 | +0.00005 | +0.00013 |

For the primary Dirichlet-0.1 scenario, Aggregate improves mean ACC over Self in all seeds, with median +0.00833 (0.833 percentage points). However, Aggregate loses to Shuffled on ACC in all three seeds, median −0.00662. The preregistered exploratory gate requires both Aggregate−Self and Aggregate−Shuffled to be positive in all three seeds and each median to reach +0.005. **The gate fails** because Aggregate−Shuffled is negative in all seeds. This matches the generated report’s “screening threshold not met” status.

The directions depend on the quality metric. Against Self, Aggregate’s primary-scenario NMI is lower in two of three seeds (median difference −0.00619), while ARI is higher in all three (median +0.00328). Against Shuffled, Aggregate’s NMI is higher in all three (median +0.01110), ARI is higher in two of three (median +0.00353), but ACC is lower in all three. These metric disagreements do not support a single unqualified “better clustering” claim.

The ACC loss against Shuffled is broad across clients: Aggregate benefits only 1/6 clients in each primary-scenario seed and harms 5/6. The minimum same-client paired ACC differences (Aggregate client i minus Shuffled client i) are −0.0111, −0.0243, and −0.0312. These are not the difference between Aggregate’s and Shuffled’s separately worst client scores. By comparison, Aggregate−Self benefits 5/6, 6/6, and 6/6 clients, with minimum same-client paired differences −0.0005, +0.0002, and +0.0023. Aggregate−Local benefits 4/6, 4/6, and 6/6 clients. This describes how the mean comparisons arise; clients remain nested within three seeds.

## Target and gradient diagnostics

For Dirichlet-0.1, I averaged each case’s all-round diagnostic rows first, then summarized the three seed-level values (so the thousands of edge/round/client observations do not inflate the sample size). Across-seed means of those seed summaries were:

| Target type | Target SD | Offline target Brier | Target gap (same-edge target mean: public-same minus public-different) | Fraction differing from own Self row |
|---|---:|---:|---:|---:|
| Self | 0.4129 | 0.2138 | 0.3660 | 0.0000 |
| Aggregate | 0.2686 | 0.1118 | 0.3675 | 0.4686 |
| Shuffled | 0.2620 | 0.1800 | −0.0008 | 0.5691 |

The table averages target records generated along each method’s own training trajectory; it is not a matched distribution comparison between the two training branches. In those records, the seed-averaged target SD is 0.2686 for Aggregate versus 0.2620 for Shuffled, and offline Brier is 0.1118 versus 0.1800. This is descriptive evidence that the recorded Aggregate targets along their own paths are more aligned with logged public relation truth, but the two paths are not held fixed. At a fixed anchor and snapshot, the counterfactual Aggregate and Shuffled probe targets do share a value multiset; the shuffled assignment removes the edgewise association with public same/different edges (near-zero target gap). Neither the same-anchor probe nor the trajectory-level offline Brier establishes that correct cross-client assignment causes the final ACC difference or that public truth predicts final evaluation quality. Shuffled has higher final ACC in all three primary seeds.

For an additional gradient summary, I used the Aggregate branch as a fixed anchor and, within each seed, averaged the probe rows over the recorded clients and probe rounds before averaging the three seed summaries. The resulting mean gradient cosine (private vs. weighted-public) and weighted public/private norm ratio were: Self +0.090 / 1.321; Aggregate −0.049 / 0.659; Shuffled −0.093 / 1.468. These values describe local gradients at logged snapshots only. They are correlated across probe rounds, are not seed-level outcome replications, and cannot identify why final quality differs. In particular, they do not establish that gradient conflict caused Aggregate’s ACC loss to Shuffled.

## Conclusion and limits

The full 9-case result package is internally consistent with its completion manifest, frozen source hashes, replayable target logs, and historical Local/B references. The central outcome is clear for this exploratory sample: under strong Dirichlet non-IID, Aggregate beats Self on mean ACC but is worse than Shuffled on mean ACC in every seed. Although target diagnostics averaged along the two methods’ own trajectories show better offline truth alignment for Aggregate, their evolving targets and training paths are not matched. These outcomes therefore do **not** demonstrate a final-ACC benefit from correctly assigning cross-client aggregate relations, and the preregistered exploratory screening gate fails. NMI and ARI move differently, so the conclusion is metric-specific.

This is a three-seed exploratory result on Fashion-MNIST under the registered full configuration; it is not confirmatory evidence, a general federated-learning claim, or performance confirmation for D/E. Gradient and offline truth diagnostics are descriptive and should not be used as causal explanations.

## Cluster-occupancy check over training

I inspected every stored evaluation checkpoint, separating the round-1 initialization/early update from round 20–200. This experiment newly records round 1, whereas the older non-IID runs used for Local/B reference comparison began at round 20; therefore the round-1 collapse observations below are not evidence of a new regression relative to those historical runs.

- At round 1, **all Dirichlet-0.1 seeds and methods** have at least one client with only one occupied cluster and a client with 100% largest-cluster share. This is transient: at round 20, the minimum occupied-cluster count across clients is 6–9 depending on seed/method, and by round 200 every client in every method occupies all 10 clusters.
- Dirichlet-0.5 also has one-cluster/100%-share clients at round 1 in several method/seed combinations (notably seed 505 Self/Aggregate/Shuffled and seed 606 Self); round 20 minimum occupancy is 8–9 and all clients reach 10 by round 200.
- IID starts with at least 3 occupied clusters per client at round 1, reaches 10 for all clients by round 20, and stays there.

This supports saying that a one-cluster state appears in early checkpoints for the non-IID partitions and then recovers in occupancy count. It does **not** support a blanket “no collapse” statement: through rounds 20–200, the strongest non-IID case still has substantial imbalance (up to a 0.7157 largest-cluster fraction, for Dirichlet-0.1 seed 606 Self at round 20), and occupancy can dip to 6–9 clusters for some clients before the final evaluation. Conversely, final-round 10-cluster occupancy alone does not erase that trajectory. This is a new descriptive check, not a matched historical comparison at round 1.

As context for the primary ACC result, the independently recomputed Dirichlet-0.1 Self−Local differences are −0.00517, −0.00845, −0.00467 (median −0.00517; 0/3 positive), while Shuffled−Local is +0.00678, +0.00653, +0.01107 (median +0.00678; 3/3 positive). The result pattern is therefore consistent with Self underperforming Local and Shuffled outperforming Local on ACC in this sample; it still does not isolate why, and NMI/ARI do not follow the same directions.
