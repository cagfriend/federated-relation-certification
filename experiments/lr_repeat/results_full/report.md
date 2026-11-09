# P2 LR .05 重复测量报告

技术重复：36 个运行，4 个案例。每个案例按重复编号配对 B、E、D。时间结果仅作本地探索性测量；技术重复不是独立种子证据。

## 逐案例冻结判据

| 案例 | 角色 | C1 中位 D/B 节省 | C2 中位 D/E 节省 | D/B 胜场 | D/E 胜场 | C1 | C2 | C3 | 通过 |
|---|---|---:|---:|---:|---:|---|---|---|---|
| n12_k10_dirichlet_0.1_seed1001 | healthy | 36.11% | 2.57% | 3/3 | 2/3 | True | False | True | False |
| n12_k10_dirichlet_0.1_seed1101 | new_seed | 40.87% | 8.47% | 3/3 | 3/3 | True | True | True | True |
| n6_k64_dirichlet_0.1_seed1002 | known_failure | 25.93% | 1.74% | 3/3 | 2/3 | True | False | True | False |
| n6_k64_dirichlet_0.1_seed1101 | new_seed | 30.90% | 0.79% | 3/3 | 2/3 | True | False | True | False |

C1/C2/C3 均按单案例判定，不合并案例或种子。C1 要求中位 D/B 节省至少 10%；C2 要求中位 D/E 节省至少 3%；C3 要求两组比较各至少 2/3 次获胜。

准备时间包含已知污染的案例保留 NA；原始准备字段保存在 runs.csv，未以零替代。准备时间合计不是本表统计对象。checkpoints.csv 仅含 B 的首个技术重复共享质量轨迹。
