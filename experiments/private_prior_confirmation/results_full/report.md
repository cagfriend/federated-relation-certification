# Private-prior B/E/D confirmation report

Mode: **formal confirmation**.

Technical repeats are averaged within each seed and method before paired D/B and D/E comparisons. The seed is the statistical unit; n=3 is small, so this report gives per-seed ratios and their min/max without significance claims.

Raw `head_pipeline_seconds`, measured stage time and generation time are listed for every technical repeat in `raw_runs.csv`. Shared preparation and loading costs are separate fields. Preparation is a one-time shared cost and is not added three times to a repeat total.

Quality is reported without an ACC-improvement requirement. `quality.csv` contains client-level ACC, NMI, ARI, occupied clusters and largest-cluster fraction at rounds 160/180/200, plus C0/C3 teacher same-cluster rates averaged over rounds 161–200.

## dirichlet_0.1

D/B median: 0.6071 (min–max 0.5907–0.6301); C1 PASS.
D/E median: 0.8755 (min–max 0.8395–0.8834); C2 PASS.
Seed wins: D beats B in 3/3, and E in 3/3; C3 PASS.
Quality guard: PASS; overall formal decision: PASS.

Per-seed paired ratios: 1201: D/B=0.6071, D/E=0.8755; 1202: D/B=0.6301, D/E=0.8395; 1203: D/B=0.5907, D/E=0.8834

## iid

D/B median: 0.6092 (min–max 0.5471–0.6141); C1 PASS.
D/E median: 0.8333 (min–max 0.8323–0.9340); C2 PASS.
Seed wins: D beats B in 3/3, and E in 3/3; C3 PASS.
Quality guard: PASS; overall formal decision: PASS.

Per-seed paired ratios: 1201: D/B=0.5471, D/E=0.8333; 1202: D/B=0.6092, D/E=0.8323; 1203: D/B=0.6141, D/E=0.9340
