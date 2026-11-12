# Independent result review: local public-LR experiment

Date: 2026-11-12
Scope: read-only verification of the two formal records in `experiments/local_public_lr/results_full`; no edits to source or raw results, no training, and no publication. This document is the only reviewer-authored output.

## Judgment

**The records and stated late recovery decision pass independent checks.** In this single strong/IID/seed1001 case, local LR passes the registered 160/180/200 rule while the matched 0.05 baseline fails. This means the local branch released the severe-collapse flag at those late checkpoints. It does not mean the intervention prevented collapse or produced semantically healthy clusters.

## Raw record and baseline verification

I opened both 200-round raw JSON records. Each has test checkpoints at 20 through 200, the same initial-head digest (`5363d4ff…f68c46`) and graph digest (`999b5382…30f5db`). The recorded weights are baseline `[0.5]*6` and local `[0.125,0.5,0.5,0.125,0.5,0.5]`, corresponding to effective public LR 0.05 for all baseline clients and 0.0125 only for clients 0 and 3 in the intervention. The other four clients remain at 0.05.

I independently compared the baseline’s 200 round records after removing timing fields with historical `quantity_heterogeneity` strong/IID/seed1001 B. All round fields, initial head, graph and all ten test checkpoints match exactly. The local branch uses the same data, initial head, graph and public step schedule. The parent audit additionally reports matching private/public order digests and source/cache identity.

## Registered late recovery rule

The criterion is checked per client at all three checkpoints: at least two occupied clusters and maximum-cluster fraction strictly below 0.99. The baseline passes 12/18 client-checkpoint rows; clients 0 and 3 fail all three checkpoints as single clusters with fraction 1.0. The local branch passes 18/18:

| Client | Private count | 160 clusters / max fraction | 180 clusters / max fraction | 200 clusters / max fraction |
|---:|---:|---:|---:|---:|
| 0 | 100 | 2 / 0.930125 | 2 / 0.894375 | 2 / 0.860125 |
| 1 | 400 | 9 / 0.433500 | 9 / 0.407625 | 9 / 0.400000 |
| 2 | 700 | 10 / 0.204125 | 10 / 0.192875 | 10 / 0.187875 |
| 3 | 100 | 3 / 0.980500 | 3 / 0.940125 | 3 / 0.897875 |
| 4 | 400 | 10 / 0.283000 | 10 / 0.263125 | 10 / 0.265250 |
| 5 | 700 | 10 / 0.174125 | 10 / 0.168125 | 10 / 0.160625 |

The rule only releases the predefined severe-collapse label. At round 160, client 3 is close to the cutoff (98.05% in its largest cluster). Low capacity clients also retain weak NMI: client 0 is 0.01284, 0.01546, 0.01769 and client 3 is 0.01400, 0.03834, 0.05789 at 160/180/200. That is not evidence of healthy semantic clustering.

## Earlier collapse and historical intervention references

The local change does not prevent early collapse. At round 20, client 3 is single-cluster and client 0 is at exactly 99.0%. At rounds 40, 60 and 80 both are single-cluster. At round 100 client 3 remains single-cluster and client 0 is 99.8875%; at 120 client 3 is still single-cluster; at 140 it has three clusters but remains at 99.8375%. All six first pass together at round 160. The baseline has client 3 single-cluster at round 20 and both low-capacity clients single-cluster from round 40 onward.

Earlier same-case historical diagnostic runs show that neither local LR is the only branch with late recovery. Global low-LR (all clients at 0.0125) and private-only (no public update) also pass all six at 160/180/200. Their low-capacity clients collapse earlier as well: global low-LR client 3 remains single-cluster through round 120 and first passes at 160; private-only client 3 first passes at 120, while client 0 passes at 100. These are useful same-case references, not new randomized replicates.

Across the local branch’s 82 low-capacity client-rounds from rounds 160–200, the recorded within-round changes average +0.341 percentage points in private pseudo-label fit after private SGD, −0.207 points after public SGD, and +0.312 points in public-probe largest-cluster fraction after public SGD. In other words, private updates modestly improve the fit/concentration measures on average, while public updates partly increase probe concentration again. This is descriptive on one coupled trajectory; it does not identify a unique mechanism.

## Integrity and limits

The raw recovery CSV contains all 36 rows (two branches × six clients × three late checkpoints); missing clients/checkpoints do not appear. The rates file agrees with the per-client weights above. The power log has 12 samples, all AC-on, with no gap warnings. Parent-side audit reports the completion manifest/source/cache checks and 16 regenerated report files byte-equal.

This remains one IID seed and one paired case. Local LR changes later teacher feedback for the whole coupled system, even though only clients 0 and 3 get a different public rate. Historical global low-LR and private-only branches also recover late, so local LR is a viable candidate intervention here, not a uniquely established cause or a general fix. No ACC gain or certification-performance claim follows.
