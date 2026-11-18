# STL-10 multi-client encoder fallback

Teacher rates use rounds 161–200. Test largest cluster uses checkpoints 170/180/190/200.

| Seed | Partition | Arm | Encoders | Status | Client 1 teacher | Client 1 test largest | Worst test largest | Mean ACC |
|---|---|---|---|---|---:|---:|---:|---:|
| 1207 | dirichlet_0.1 | previous | [2, 3, 5, 2, 4, 5] | blocked | — | — | — | — |
| 1207 | dirichlet_0.1 | all_client_fallback | [2, 1, 2, 2, 4, 5] | completed | 11.28% | 20.75% | 28.43% | 20.03% |
| 1207 | dirichlet_0.1 | client2_only_recovery | [2, 3, 2, 2, 4, 5] | completed | 90.81% | 95.80% | 95.80% | 18.78% |
| 1208 | iid | previous | [2, 3, 5, 2, 4, 5] | completed | 71.19% | 84.05% | 84.05% | 18.40% |
| 1208 | iid | all_client_fallback | [2, 2, 5, 2, 4, 5] | completed | 11.78% | 16.85% | 25.30% | 19.15% |
