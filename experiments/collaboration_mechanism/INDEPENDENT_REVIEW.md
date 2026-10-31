# Independent code review: collaboration mechanism experiment

Date: 2026-10-31 (final implementation review)
Scope: read-only review of `experiments/collaboration_mechanism/{engine.py,targets.py,diagnostics.py,run.py,test_mechanism.py,report.py}` and relevant frozen `public_scaling` semantics. No source code was edited and no formal training or data download was run.

## Findings and final status

The reference-validation concern from my first review is now resolved. One clarification to that review: the earlier `check_reference` already compared `old['clients'] != new['clients']` as complete client-record lists, so it compared each client's metrics, not merely the number of clients. The remaining gap was that it did not compare each metric's `mean` object and did not enforce unique, complete reference key sets. The final implementation checks exact, duplicate-free `(round, method)` coverage for Local/B trajectory rows and evaluation rows, then compares the full evaluation metric object (including `mean` and `clients`) after mapping `B` to `Aggregate`. New negative tests reject re-sealed duplicate round rows, duplicate metric rows, and a changed reference mean. Existing head-digest, per-round traffic, and summary traffic checks remain.

Severity: resolved; no blocking issue found in the final reviewed code.

## Mechanism and fairness checks

- **Targets:** `Self` is each client's own hard relation row from that branch's own post-private snapshot. `Aggregate` is the per-edge relation count divided by client count, broadcast identically to all clients, including each client's contribution. `Shuffled` permutes that aggregate count vector using one deterministic permutation per seed/round, shared across clients. Therefore it preserves the aggregate target-value multiset and changes its edge assignment.
- **Independent trajectories:** all four branches instantiate deterministic identical initial heads and run actual private SGD; public updates are run for Self, Aggregate, and Shuffled. Per-client/round data orders are deterministic and branch-independent, so the branch target is the intended learning intervention. A rotating method execution order is used. Local receives no public update or traffic.
- **Snapshot timing:** each non-Local branch generates teacher labels after its private epoch and before its public epoch from copied `(w,b)` arrays. Those frozen labels/relations are the targets for that branch's public step. Local computes an equivalent relation snapshot only for scheduled probes.
- **Probe isolation:** probes use identical fixed private IDs and public edge IDs for all three target types at a given round/anchor/client, and evaluate each target against the same copied student snapshot. Probes call analytic gradient helpers without applying updates. The fixture test compares final head digests and traffic with probes enabled/disabled and varies public truth; all are identical.
- **Truth isolation:** public labels are converted to hard relation truth and used only to add offline Brier/gap fields to target records. They do not enter target construction, optimizer calls, or diagnostic gradients.
- **Replay and records:** relation logs include packed local relation rows, raw-count/permutation/applied-target digests, target histograms, and are reconstructed and validated. Case validation checks target record counts, target shape, all round/method coverage, expected probe coverage, equal training budgets, final-summary consistency, payload checksum, and reconciles traffic totals.
- **Reporting:** report computes paired client and seed summaries, while cross-seed comparisons use one mean-ACC difference per seed. In the primary `dirichlet_0.1` partition, the joint screening status only passes if both Aggregate−Self and Aggregate−Shuffled are positive on all three seeds and each median is at least 0.005. The label is exploratory and requires new seeds for confirmation. Smoke runs explicitly cannot determine the threshold; report output also retains paired NMI/ARI results and partition identifiers. Timings are diagnostic, not a D/E performance claim.

## Verification run

Ran all six fixture unit tests after the final changes:

```text
python -m unittest experiments.collaboration_mechanism.test_mechanism -v
Ran 6 tests in 0.524s — OK
```

Coverage includes target/permutation replay, Aggregate versus old B and Local semantics, probe/training isolation and truth-label independence, zero/opposed gradient handling, rejected duplicate/tampered reference records, and joint screening/smoke gate behavior. These are fixture tests, not full-run evidence.

## Acceptance

The final implementation matches the stated target definitions, passes the six allowed fixture tests, and now validates old Local/B reference trajectories and complete evaluation objects with duplicate/missing-key checks. I accept the reviewed code at this stage. Main-agent smoke, resume, and artifact audits remain separate evidence.


## Primary-agent acceptance

Two GPT-6 Luna agents (high reasoning) were used: one implemented and manually checked report.py; one independently reviewed target definitions, branch fairness, snapshot/probe isolation, reference validation and reporting, and ran six fixture tests. The primary agent inspected their code and evidence, requested and verified full reference-key/mean validation, partition labels, NMI/ARI comparisons, and smoke gate exclusion. Final official smoke: 9 cases, 36 trajectories, 81 replayable target logs, 648 gradient rows, 54 historical Local/B round-method matches, zero mismatches; resume preserved 9 cases. All 26 smoke-output hashes verified and seven regenerated reports were byte-identical; 36 resealed semantic corruptions were rejected. All nine formal configurations and existing caches passed read-only preflight, and 60 prior non-IID output files and all core/preparation Python sources remained unchanged. The final runner additionally verifies all four official dataset checksums on fresh and resume paths. Accept code for the specified exploratory mechanism experiment; formal quality evidence has not been produced.
