# STL-10 encoder snapshot validation

Tail summaries use rounds 161–200 and test checkpoints 170/180/190/200.
The selector uses only private cluster occupancy and unlabeled public occupancy.
ACC guard permits a drop of one percentage point for the target, network mean and worst client.

| Seed | Partition | Selected | Final-step baseline | Teacher tail baseline → selected | Test largest tail baseline → selected |
|---|---|---:|---|---:|---:|
| 1205 | iid | 3 | completed | 26.56% → 10.11% | 51.80% → 14.77% |
| 1205 | dirichlet_0.1 | 4 | completed | 11.07% → 11.07% | 17.00% → 17.00% |
| 1206 | iid | 3 | initialization_blocked | — | — |
| 1206 | dirichlet_0.1 | 4 | completed | 12.52% → 12.52% | 21.75% → 21.75% |
| 1207 | iid | 3 | initialization_blocked | — | — |
| 1207 | dirichlet_0.1 | 3 | initialization_blocked | — | — |
| 1208 | iid | 3 | initialization_blocked | — | — |
| 1208 | dirichlet_0.1 | 3 | initialization_blocked | — | — |
| 1209 | iid | 3 | completed | 25.24% → 14.89% | 44.30% → 19.95% |
| 1209 | dirichlet_0.1 | 3 | initialization_blocked | — | — |

| Recovery step (client 2) | Status | Teacher tail | Test largest tail | Target ACC |
|---|---|---:|---:|---:|
| 5 | initialization_blocked | — | — | — |
| 3 | completed | 67.58% | 88.60% | 13.60% |
| 2 | completed | 11.75% | 17.55% | 19.80% |
