# Quantity heterogeneity test handoff (2026-11-10)

Test file: `experiments/quantity_heterogeneity/test_run.py`

Command:

```powershell
python -m unittest experiments.quantity_heterogeneity.test_run -v
```

Final frozen-source result (run by the main agent): **6 tests passed in 20.156 seconds** (`OK`). No formal experiment was started by this test task; all generated fixture/cache files used a `TemporaryDirectory` under the package and were cleaned automatically.

Coverage:

1. Full/smoke capacity presets, 54/18 run schedules, six memory jobs, separate profile regimes, and exact full equal-profile P3 N6 spec.
2. Deterministic capacity partitions across all profiles, both partition modes, and seeds 1001/1002/1003; exact sizes, unique full coverage, and global class totals; invalid capacities rejected.
3. Equal-capacity partition outputs match the legacy implementation byte-for-byte at the array/diagnostic level for both modes and all three seeds.
4. Fixture cache verifier rejects a changed profile and a tampered pseudo-label array; original bytes are restored and the cache passes again.
5. Equal-profile fixture engine matches legacy B/E/D trajectories and metrics; strong-profile fixture B/E/D paired outputs match, and memory D omits metrics/audits.
6. Runner record/group verification accepts strong-profile capacities, checks the round-2-only evaluation schedule for a two-round fixture, rejects resealed incorrect private capacity, and exports timing-free rows.

The tests use synthetic labels and generated STL-format fixtures. Their outputs validate implementation consistency and integrity checks, not model quality or formal experiment evidence.
