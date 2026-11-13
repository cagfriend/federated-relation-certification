# Independent review: local public-LR confirmation

Review date: 2026-11-13. Scope: static review of the final confirmation runner/report source and read-only inspection of the three full raw records, manifests, and the historical completed seals. No training, source edits, or Git operations were performed.

## Verdict

**The registered late severe-collapse criterion passes in the three recorded cases (54/54 client-checkpoint observations), and the raw runs pass the package record verifier.** The output directory manifests and historical finished seals also verify.

## Results at registered checkpoints

Each cell is `occupied clusters / largest-cluster fraction` from the raw `metrics` record (test set), clients 0–5 in order. The criterion is more than one occupied cluster and a largest-cluster fraction strictly below 0.99 at rounds 160, 180, and 200. All six clients are present at every required checkpoint.

| Case | Round 160, clients 0–5 | Round 180, clients 0–5 | Round 200, clients 0–5 | Result |
|---|---|---|---|---|
| seed 1001, Dirichlet 0.1 | 2/.9326, 10/.3936, 10/.2039, 3/.7505, 9/.2628, 9/.2050 | 2/.9094, 10/.3434, 10/.1978, 3/.7321, 9/.2319, 9/.1923 | 2/.8858, 10/.3644, 10/.1973, 3/.7149, 9/.2374, 9/.1838 | 18/18 pass |
| seed 1002, IID | 2/.9784, 9/.2291, 10/.1629, 3/.7078, 7/.2479, 10/.1890 | 2/.9456, 9/.2406, 10/.1588, 3/.6835, 8/.2185, 10/.1811 | 2/.9163, 9/.2280, 10/.1569, 3/.6604, 9/.2200, 10/.1715 | 18/18 pass |
| seed 1002, Dirichlet 0.1 | 5/.9766, 7/.4051, 10/.3750, 5/.7195, 8/.2875, 10/.2155 | 5/.9445, 7/.3776, 10/.3575, 6/.6870, 9/.2768, 10/.2153 | 5/.9068, 7/.3974, 10/.3444, 6/.6525, 9/.2440, 10/.2159 | 18/18 pass |

Client 0 is the tightest margin in the two seed-1002 cases: its round-160 largest-cluster fractions are 0.9784 (IID) and 0.9766 (Dirichlet 0.1). Both meet the fixed criterion. Client 0 in seed-1001 Dirichlet is also the least diverse client at the late checkpoints, with two occupied clusters and fraction 0.9326 at round 160.

## Adverse and boundary evidence

The late-only criterion should not obscure early severe concentration. In the seed-1001 Dirichlet case, client 0's test prediction is a single cluster at rounds 20 and 40; at round 80 it has two clusters but a 0.9985 largest-cluster fraction. In seed-1002 IID, client 0 is single-cluster at rounds 40, 80, 100, and 120; it reaches two clusters at round 140 but remains at 0.9980. In seed-1002 Dirichlet, client 0 is single-cluster at rounds 40, 80, and 100, has two clusters at 0.99925 at round 120, and has five clusters at 0.994125 at round 140. These observations are early events, not failures of the pre-registered late checkpoints.

The initial diagnostics also show difficult starts: seed-1002 IID client 0 has a single public cluster (fraction 1.0) in its initial public-probe prediction; seed-1002 Dirichlet client 0 has two clusters with largest fraction 0.9941. The round-1 T0 public-probe diagnostics show the same respective patterns. Thus, the eventual late release is not evidence that early collapse was absent or that all clients have generally healthy semantic clusters.

At round 200, mean test ACC is 0.1706 (seed-1001 Dirichlet), 0.1793 (seed-1002 IID), and 0.1660 (seed-1002 Dirichlet). There is no registered ACC-improvement threshold; these values are descriptive. No new baseline was run, so they do not establish an ACC gain over baseline. The matching historical quantity B run is a reference only. Historical low-capacity baseline coverage remains 40 rounds; unrecorded late baseline fields remain unavailable. The exploratory seed-1001 IID local-LR case and exploratory run count do not enter the three-case denominator.

## Source and provenance checks

- The final `design.py` schedules exactly the three registered `local_lr` B cases at 200 rounds, evaluation every 20 rounds, capacities `[100, 400, 700]` repeated twice, with `public_weight=.5` and private `head_lr=.1`. The per-client public weights are `[.125, .5, .5, .125, .5, .5]`, which produce effective public learning rates `[.0125, .05, .05, .0125, .05, .05]`. Source uses the frozen `experiments.local_public_lr.engine.run` implementation.
- `report.py` evaluates the specified rounds 160/180/200 across six clients, treats absent clients/checkpoints as failure, requires all three case IDs for an all-cases pass, and counts only `local_lr`. Its history export reads fields actually present and emits unavailable late-stage data as NA. It makes no accuracy or certification-speed claim.
- For each new raw record, the initial head digest and graph digest match the matching 200-round quantity B record. The recorded public probe identities are consistent with the per-seed probe selection: seed 1001 has its own public-ID/local-index hashes; seed 1002's IID and Dirichlet cases share the same probe hashes. The actual probe arrays are recorded in each raw run. The expected run specifications and diagnostics report six clients and the declared private capacities.
- Independent byte-level verification passed for all 22 files listed in this output's `completed.json`; `finished.json` correctly hashes `completed.json`. The quantity, prior-local, and low-capacity historical outputs also passed their completed-file hashes and finished seals (79, 22, and 27 listed files respectively).
- The confirmation package's exact `run.verify_record` path passed on all three stored raw records. For each record, `run.seal(dict(record))` reproduced the stored `run_sha256`; the complete record verifier returned `True`.
- The pre-run execution-policy amendment allows battery or unknown power status for this quality/stability run. Power status is logged; no timing or plugged-in operation claim is made.

## Acceptance

The pre-registered numerical release check and the static design/report logic pass for the observed data. **The run and report logic, three raw records, and the pre-registered late severe-collapse criterion pass review.** The result may be reported as a three-case late severe-collapse release, with the early-collapse and single-seed/case boundaries above. Do not add timing, accuracy-improvement, or certification-speed claims.

Reviewed files: `experiments/local_public_lr_confirmation/PREREGISTRATION.md`, `design.py`, `run.py`, `report.py`, `engine.py`, `results_full/runs/*.json`, and `results_full/{completed.json,finished.json,environment.json,report.md,recovery.csv}`; plus the three historical result manifests named in `environment.json`.


