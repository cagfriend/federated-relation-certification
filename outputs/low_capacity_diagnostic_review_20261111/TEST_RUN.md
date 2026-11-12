# Low-capacity diagnostic test record (2026-11-11)

Test file: `experiments/low_capacity_diagnostic/test_run.py`

Command:

```powershell
python -m unittest experiments.low_capacity_diagnostic.test_run -v
```

Result: **4 tests passed in 6.724 seconds** (`OK`). Scikit-learn emitted expected fixture warnings that some synthetic feature sets had fewer distinct clusters than the requested K=10; all tests passed. No formal training was started. Fixture data and prepared caches were created inside a package-local `TemporaryDirectory` and cleaned up automatically.

Coverage:

1. Full and smoke branch rounds, evaluation cadence, public LR, and scheduled case counts.
2. Recovery rule across all six clients and checkpoints, including rejection of a missing checkpoint, missing client, and largest-cluster fraction exactly 0.99.
3. Deterministic probe selection/manifest and unchanged NumPy global RNG state.
4. Fixture integration: probe-enabled/disabled baselines match the frozen quantity B engine in complete non-time rows, metrics, graph and head digests; probe records contain T0/T1/T2 fields. `private_only` skips the public update while retaining private work and has identical T1/T2 heads. `low_lr` calls the existing student update with public weight 0.125.

These fixture checks validate implementation behavior and do not provide model-quality or formal experiment evidence.
