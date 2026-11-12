# Local public-LR diagnostic report

Single frozen STL-10 case: strong / IID / seed1001.

Two new full-length B trajectories; baseline passed the exact historical training replay gate. No performance conclusions.

|Branch|Rounds|Severe-collapse check|
|---|---:|---|
|baseline|200|not_released|
|local_lr|200|released_severe_collapse|

Baseline: all clients effective public LR 0.05. Local intervention: clients 0/3 use 0.0125; others retain 0.05. Both use two public steps. Actual client weights/rates are in client_rates.csv.

Recovery is checked for all six clients at every prescribed late checkpoint: occupied clusters > 1 and maximum cluster fraction < 0.99. Missing values fail. This is release of severe collapse, not sufficient semantic health; no ACC improvement criterion.

late_comparison.csv lists every late client/checkpoint, including historical all-client low-LR and private-only references when available. stage_effects.csv records within-round changes; stage_contrasts.csv subtracts the matched new baseline, not independent causal effects.

T0 precedes private SGD; T1 is the actual teacher after private SGD; T2 follows public SGD. Baseline and local_lr both have real 200-round instrumentation. Historical test fields are exported separately; unrecorded fields are never reconstructed.

Lowering only local learning rates still changes later coupled teacher feedback. A single configuration cannot establish a unique cause or generalize to non-IID. Diagnostic time is not certification speedup evidence.
