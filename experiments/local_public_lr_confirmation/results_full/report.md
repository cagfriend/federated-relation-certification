# Local public-LR confirmation

Three pre-registered local-LR confirmation cases.

Registered cases released: 3/3. An absent case remains in the denominator and prevents an all-cases pass.

| Case | Seed | Partition | Checkpoints passing / 18 | Result |
|---|---:|---|---:|---|
| strong_dirichlet_0.1_seed1001 | 1001 | dirichlet_0.1 | 18/18 | released severe collapse |
| strong_iid_seed1002 | 1002 | iid | 18/18 | released severe collapse |
| strong_dirichlet_0.1_seed1002 | 1002 | dirichlet_0.1 | 18/18 | released severe collapse |

Only `local_lr` was newly run: clients 0 and 3 use effective public LR 0.0125, other clients use 0.05. Each run uses B, full private data, and two public optimizer steps per client per round. No new baseline run is included.

The pre-registered release criterion requires all six clients to occupy more than one cluster and have largest-cluster fraction below 0.99 at rounds 160, 180, and 200. Missing checkpoints fail. This is not a general healthy-clustering or accuracy-improvement claim.

Historical quantity B tests and low-capacity baseline/global-low/private-only tests are listed only at their recorded checkpoints. The earlier single-case local-LR result is marked exploratory. Unrecorded late historical fields remain missing; this report does not infer them.

The experiment does not claim certification speedup. Reducing two clients’ public update rate also changes later coupled teacher feedback.
