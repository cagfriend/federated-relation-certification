# Local public-LR confirmation

Status (2026-11-12): main-agent unit tests, smoke, resume and input preflight passed. Final independent review remains pending because sub-agents reached their usage limit. Formal training has not started. See VALIDATION.md.

This package runs the three remaining strong-profile cases registered in `PREREGISTRATION.md`. It reuses `experiments.local_public_lr.engine.run` and runs only the `local_lr` branch. It never schedules a new 200-round baseline.

The case list is seed 1001 / Dirichlet alpha 0.1, seed 1002 / IID, and seed 1002 / Dirichlet alpha 0.1. Seeds and partitions have appeared in earlier experiments; the confirmation rule is the new intervention. Each formal run uses six clients, capacities `[100, 400, 700]` repeated twice, public M=16384, two public steps per round, and 200 rounds with evaluations every 20 rounds. Clients 0 and 3 use public weight 0.125 (effective public LR 0.0125); the remaining clients use weight 0.5 (effective public LR 0.05). The private LR remains 0.1.

## Run

Start the smoke matrix with:

```powershell
python -m experiments.local_public_lr_confirmation.run --preset smoke --output experiments/local_public_lr_confirmation/results_smoke
```

The smoke preset creates a separate synthetic cache for each case and runs three rounds. It is only a code-path check.

Start the formal matrix with:

```powershell
python -m experiments.local_public_lr_confirmation.run --preset full --output experiments/local_public_lr_confirmation/results_full
```

Formal execution checks AC power, sets one BLAS thread in each worker, records power every 15 seconds, and verifies the frozen quantity, local-LR, and low-capacity source manifests. It does not download or modify those source results. It consumes the prepared input pointers from the full quantity-heterogeneity result set.

To resume an interrupted output directory, pass `--resume` with the same output path. Each completed run is verified and preserved. A completed output is rechecked against its completion manifest and finished seal.

## Results and interpretation

Each new run contains per-client T0/T1/T2 probe summaries, update losses and parameter deltas, the fixed public probe identity, and test metrics at the registered checkpoints. `recovery.csv` checks every client at rounds 160, 180, and 200; each must occupy more than one cluster and have largest-cluster fraction below 0.99. Missing clients or checkpoints fail.

Historical test metrics are exported with a source label. The full-length quantity B record supplies the matching 200-round reference. Low-capacity baseline history remains its recorded 40 rounds; global-low and private-only diagnostic records are retained at their actual checkpoints. Prior one-case local-LR results are marked exploratory and do not increase the confirmation sample count. Unrecorded historical late-stage fields are never reconstructed.

The criterion reports release from severe collapse only. It does not require an ACC increase, establish semantic clustering health, isolate one cause, or measure certification speedup.
