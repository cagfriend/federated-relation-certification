# Independent review: performance confirmation results

Review date: 2026-11-01  
Scope: read-only audit of `experiments/perf_confirmation/results_full`; raw run records and source were not modified.

## Reviewed evidence and method

I independently read all 72 `runs/*.json` records (72 found), using each run's `summary[method]` timing, final `metrics` record, and 200 `round_records`. I grouped by partition, seed, tier and method; averaged repeat 0/1 within each seed; then formed paired D/B and D/E ratios at the seed level. This reproduces the pre-registered order of operations. I also compared the resulting primary ratios with `paired_summary.csv` and `summary.json`. The pre-registered rule is in `experiments/perf_confirmation/PREREGISTRATION.md`.

## Pre-registered C1–C3 decision, candidate tier 2048

| Partition | C1: median D/B ≤ 0.90 | C2: median D/E < 1.00 | C3: wins D/B, D/E | Result |
|---|---:|---:|---:|---|
| Dirichlet 0.1 | 0.759082 (pass) | 0.919472 (pass) | 3/3, 3/3 (pass) | Confirmed |
| IID | 0.757170 (pass) | 0.942726 (pass) | 3/3, 3/3 (pass) | Confirmed |

Seed-level head seconds (D, comparator, ratio) behind the candidate-tier checks:

- Dirichlet 0.1 D/B: seed 707 56.3102/74.1820/0.759082; 808 58.4383/72.0651/0.810910; 909 71.7672/103.2035/0.695395.
- Dirichlet 0.1 D/E: seed 707 56.3102/61.2419/0.919472; 808 58.4383/60.7780/0.961504; 909 71.7672/80.5945/0.890473.
- IID D/B: seed 707 55.6915/75.8593/0.734143; 808 56.3078/71.8390/0.783806; 909 54.6609/72.1910/0.757170.
- IID D/E: seed 707 55.6915/57.7516/0.964329; 808 56.3078/60.4519/0.931448; 909 54.6609/57.9817/0.942726.

Thus the pre-registered conclusion is **both partitions confirmed for the 2048-tier compute-time criteria**. This describes the three observed new seeds and the specified serial process timing protocol.

## Quality guardrail

Using `quality_guardrails.csv` and the final per-run metrics, each 2048-tier final mean ACC is lower than its full-tier reference by 0.20–0.46 percentage points, within the pre-registered 1 pp bound in all six partition/seed pairs:

| Partition | Seed | 2048 minus full final mean ACC | Guardrail |
|---|---:|---:|---|
| Dirichlet 0.1 | 707 | −0.462 pp | Pass |
| Dirichlet 0.1 | 808 | −0.333 pp | Pass |
| Dirichlet 0.1 | 909 | −0.203 pp | Pass |
| IID | 707 | −0.418 pp | Pass |
| IID | 808 | −0.372 pp | Pass |
| IID | 909 | −0.353 pp | Pass |

This guardrail is descriptive and is not an additional timing acceptance condition.

## Maximum repeat noise and where it comes from

`timing_noise.csv` reports a maximum relative repeat difference of **61.0461%** for `dirichlet_0.1 / seed 909 / m16384_fixed8_priv2048 / E / head_pipeline_seconds`. The same pair has a 53.2479% generation-time difference. Inspecting the raw JSON identifies the two runs as `...seed_909_E_rep0.json` and `...seed_909_E_rep1.json`:

- Repeat 0: head 55.9946 s; generation 13.8490 s; process wall 93.7952 s.
- Repeat 1: head 105.1944 s; generation 23.8989 s; process wall 162.6046 s.
- Both records contain 200 rounds. Repeat 1's per-round `pipeline_seconds` exceeds repeat 0's in **all 200 rounds**; average per-round pipeline is 0.5260 s versus 0.2800 s. The largest individual per-round pipeline difference is 0.4279 s. Public-phase time is also higher in all 200 rounds; private-phase time is higher in all 200 rounds. No single round explains the accumulated gap.
- For comparison, `timing_noise.csv` gives the next largest head relative differences as D for this same partition/seed/tier at 46.6818%, then B at 41.1279%; the next-largest listed head pair outside that triple is E at Dirichlet 0.1/seed 707/candidate tier at 7.7218%.

The evidence points to a broad run-level speed shift across this triple, not an isolated slow round. It does **not** identify its cause. There is no user-confirmed pause/hibernation event attached to the pair, so I do not assign a cause or apply an exclusion. Under the frozen rules both repeats remain included. The median and win-count criteria still pass when computed with the prescribed repeat-averaging process; the high noise is a material caveat for interpreting precision and reproducibility.

## Other consistency evidence and interpretation limits

- All 72 records are present. Existing report artifacts state 12/12 (partition × seed × tier) trajectory blocks checked with zero mismatches; the aggregate artifacts' C1/C2/C3 and guardrail values agree with the independent calculations above.
- The full-tier reference is secondary context, not part of C1–C3. Results do not establish parallel or end-to-end federated system latency: the frozen primary metric is in-process `head_pipeline_seconds` from one-method-at-a-time serial processes. Only three seeds were specified, so ratios are observed seed summaries, not confidence intervals.
- Timing noise should be reported alongside the confirmation. The 61.05% maximum cannot be dismissed as a single-round outlier, and these records alone cannot distinguish host load, power/thermal state, scheduling effects, or another cause.
