# Local public-LR confirmation: remaining three cases

Plan reference: approved plan and documentation commit `e3dce2b4a9c02a81310e550d81e6e5fe16bace67`. These are previously used seeds and data configurations; only this local-LR rule is new for the three listed cases. The experiment reuses the frozen `local_public_lr` engine and does not launch a new 200-round baseline.

| seed | partition | clients | private capacities | branch |
|---:|---|---:|---|---|
| 1001 | Dirichlet alpha 0.1 | 6 | [100, 400, 700] repeated twice | local_lr |
| 1002 | IID | 6 | [100, 400, 700] repeated twice | local_lr |
| 1002 | Dirichlet alpha 0.1 | 6 | [100, 400, 700] repeated twice | local_lr |

Each full case runs B only for 200 rounds with evaluation every 20 rounds. Clients 0 and 3 use effective public learning rate 0.0125; the other four use 0.05. The main spec retains `public_weight=0.5`, private learning rate 0.1, and two public optimizer steps per client per round. Private data, teacher generation, full graph aggregation, public data and fixed probes use the existing strong quantity cache and `local_public_lr.engine.run` implementation.

The full matrix has three new long runs and no new baseline runs. The existing 200-round quantity B records, completed manifest and cache identity are verified and frozen for these cases. The earlier one-case local-LR result is frozen as exploratory history only. Completed local public-LR baseline and global-low/private-only diagnostic records are also frozen; historical fields that were never recorded remain missing and are never reconstructed. The new confirmation runs must match initial head, graph and probe selection with their quantity reference.

At rounds 160, 180 and 200, every client must occupy more than one cluster and have largest-cluster fraction below 0.99. Missing checkpoints or clients fail. This is a severe-collapse release check only. There is no ACC improvement requirement, no new health threshold, no certification-speed claim, and no claim that one client’s intervention isolates a unique cause.

Smoke uses the same three identities with independent synthetic caches, six clients, M=128, probe size 32 and three rounds with per-round evaluation. It is a code-path check and does not count as evidence. Resume preserves and verifies every already-written run. Formal runs require one BLAS thread, AC power, per-worker power checks, and a 15-second parent power log.
