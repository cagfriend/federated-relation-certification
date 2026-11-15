# Private-prior confirmation: independent statistical review

Scope: independently recomputed the timing and quality criteria from all 54 JSON files in `experiments/private_prior_confirmation/results_full/runs/`, using the frozen rules in `experiments/private_prior_confirmation/PREREGISTRATION.md`. No experiment code or training was changed or run. Timing values below use each raw run's `summary[method].head_pipeline_seconds`; technical repeats are averaged within seed/method before ratios.

## Completeness and timing criteria

Found exactly 54 distinct run records (18 seed × partition × method cases, each with repeats 0/1/2), with no duplicate case/repeat keys.

| Partition | Seed | B mean s | E mean s | D mean s | D/B | D/E |
|---|---:|---:|---:|---:|---:|---:|
| Dirichlet α=.1 | 1201 | 59.4005 | 41.1853 | 36.0594 | 0.6071 | 0.8755 |
| Dirichlet α=.1 | 1202 | 56.5246 | 42.4255 | 35.6168 | 0.6301 | 0.8395 |
| Dirichlet α=.1 | 1203 | 56.6898 | 37.9085 | 33.4869 | 0.5907 | 0.8834 |
| IID | 1201 | 59.0367 | 38.7603 | 32.2983 | 0.5471 | 0.8333 |
| IID | 1202 | 56.6018 | 41.4321 | 34.4820 | 0.6092 | 0.8323 |
| IID | 1203 | 60.9359 | 40.0621 | 37.4194 | 0.6141 | 0.9340 |

| Partition | median D/B | range | C1 | median D/E | range | C2 | wins D vs B / E | C3 |
|---|---:|---:|---|---:|---:|---|---:|---|
| Dirichlet α=.1 | 0.6071 | 0.5907–0.6301 | Pass | 0.8755 | 0.8395–0.8834 | Pass | 3/3, 3/3 | Pass |
| IID | 0.6092 | 0.5471–0.6141 | Pass | 0.8333 | 0.8323–0.9340 | Pass | 3/3, 3/3 | Pass |

## Timing variation and unfavorable observations

I retained all measured repeats. Repeat vectors in seconds (repeat order 0/1/2):

- IID 1201: B 63.192/57.738/56.180; E 39.814/37.412/39.055; D 33.087/32.017/31.791.
- IID 1202: B 60.442/54.709/54.654; E 43.466/39.659/41.172; D 34.617/34.611/34.218.
- IID 1203: B 56.706/68.213/57.888; E 39.870/40.666/39.651; D 35.867/40.658/35.733.
- Dirichlet 1201: B 61.271/58.171/58.759; E 46.324/38.983/38.248; D 34.631/38.793/34.755.
- Dirichlet 1202: B 61.462/54.328/53.784; E 45.417/41.490/40.370; D 35.717/35.786/35.348.
- Dirichlet 1203: B 57.369/54.430/58.271; E 38.725/37.684/37.318; D 33.173/32.983/34.304.

Largest within-case repeat CVs (population SD / mean): Dirichlet E seed1201 8.85%, IID B seed1203 8.48%, IID D seed1203 6.12%, Dirichlet D seed1201 5.36%, Dirichlet B seed1202 6.19%. The largest individual timing is IID B seed1203 repeat1 = 68.213 s; IID D seed1203 repeat1 = 40.658 s also drives the high D variation. These are unfavorable variability observations, retained under the preregistered all-complete-runs rule. D still wins every seed after mean pairing. Across the 18 runs per method and partition, ranges/CVs were IID B 54.654–68.213 s / 7.11%, E 37.412–43.466 / 3.87%, D 31.791–40.658 / 7.21%; Dirichlet B 53.784–61.462 / 4.70%, E 37.318–46.324 / 7.71%, D 32.983–38.793 / 4.63%.

## Six-case quality guard

Independently examined `quality.csv`: all six cases have 18 client-checkpoint rows (6 clients × rounds 160/180/200). Every row has at least 2 occupied clusters and largest-cluster fraction <0.99. All 12 C0/C3 last-40 teacher same-cluster fractions are ≤0.40:

| Partition / seed | C0 | C3 |
|---|---:|---:|
| Dirichlet / 1201 | 0.2131 | 0.2073 |
| Dirichlet / 1202 | 0.2061 | 0.1638 |
| Dirichlet / 1203 | 0.1763 | 0.2072 |
| IID / 1201 | 0.2060 | 0.1507 |
| IID / 1202 | 0.2450 | 0.1490 |
| IID / 1203 | 0.1385 | 0.1678 |

The individual ACC/NMI/ARI, cluster occupancy, and largest-cluster values remain available in the raw `quality.csv`; these were not selection criteria and no accuracy-improvement claim is made. Both partitions satisfy all three performance conditions and all six quality guards, hence both meet the preregistered joint confirmation rule for this sample only (n=3 seeds; no significance or global-stability claim).

## Scope and interpretation boundary

The preregistration specifies the only formal relation reference as the first B repeat (repeat0) for each case, reused for exact per-round relation/target/loss/schedule/parameter/quality matching. This review focused on timing and quality; it does not independently certify those trace hashes. The separate small regression oracle audit is an implementation audit, not an oracle run in these 54 formal processes. Formal runs have no per-round oracle or private/public probes. In particular, `certified_edges_before_refresh` and related relation/candidate accounting are algorithmic operational statistics; they are not counts of oracle-check operations. Do not describe these results as oracle validation of all 54 runs.

Evidence files: frozen rules at `experiments/private_prior_confirmation/PREREGISTRATION.md`; raw records at `experiments/private_prior_confirmation/results_full/runs/*.json`; quality source at `experiments/private_prior_confirmation/results_full/quality.csv`. The generated summary files were not used as the source for the recomputation.
