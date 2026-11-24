# 研究结论与适用边界

当前 D 使用偏置净变化，历史结果按各自实现引用。[E54–E55 同界对照](evidence/MATCHED_BASELINES_AND_FASHION_MNIST_20261123.md) · [E56–E57 耗时归因与复用确认](evidence/FASHION_MNIST_GATHER_OPTIMIZATION_20261123.md) · [活动清单](NEXT_EXPERIMENTS.md)

这个项目在公共无标签样本图上交换硬关系。B 全量计算，E 认证样本标签，D 直接认证关系。三条路径在受测的同配置轨迹上提交相同的硬关系和聚合目标。计算贡献以精确关系生成和完整头部的耗时为主，聚类质量用于确认受测训练处于可用范围。

| 研究问题 | 当前结论 | 证据 |
|---|---|---|
| 当前 D 在 STL-10 的适用规模 | M4096 的 12 组配置中 D 均为平均耗时最低的全图路径。新种子上，D/B 的完整头部判据在两种划分通过，D/E 在强非 IID 通过。Demand 在 11/12 组平均更快，应用层字节中位数增加 29.6%。 | [E54](evidence/e54_paired_boundaries/report.md) |
| 按边认证收益能否跨数据复现 | Fashion-MNIST 的 M4096 下，E55 原版 D/E 的完整头部判据在每种划分均有 2/3 个种子达标。原版 D/B 在两种划分均为 0/3，六组平均完整头部耗时均更长。 | [E55](evidence/e55_fashion_confirmation/report.md) |
| 特征收集优化能否降低完整头部耗时 | Fashion-MNIST M4096 的三个强非 IID 开发种子中，特征行拷贝是生成阶段最大的新增开销。新种子上，复用版对原版 D 通过预设验收。对 B 的完整头部判据为 IID 3/3、强非 IID 0/3。逐轮关系和训练轨迹一致，每进程使用一块 8 MiB 缓冲区。 | [E56–E57](evidence/FASHION_MNIST_GATHER_OPTIMIZATION_20261123.md) |
| D 什么时候节省关系生成时间 | E42 的 4096 档六个配置均比 B 和 E 快，分别节省 12.34%–31.69% 和 11.86%–23.81%。 | [E42 配对](evidence/e42_confirmation/comparisons.csv) |
| D 比 E 多认证了什么 | E46 在同一份 E 候选集合上额外判定约 26% 的边。各自使用连续缓存时，D 在三个规模相对 E 少重算约 42%–44% 的端点。 | [E46 机制图](evidence/e46_mechanism/mechanism.pdf) |
| 浮点边界在哪里 | E47 的 13 个合成实例中，五个在大数相消或长前缀下出现 E/D 对全量 B 的关系差异，独立重跑结果一致。 | [E47 正式报告与反例](evidence/MECHANISM_AND_NUMERICAL_BOUNDARY_20261121.md) |
| 关系生成收益能否兑现到完整头部 | E43 的 4096 档，IID 中 D/B 有 3/3 格达标，完整头部省 8.18%–10.57%。D/E 有 2/3 格达标。强非 IID 中两项均为 0/3。 | [E43 完整报告](evidence/e43_full_training/report.md) |
| 强非 IID 的差异是否持续 | E44 的两个受测配置相对 B 分别省 5.16% 和 4.94%，未检出持续的非生成额外耗时。 | [E44 分阶段](evidence/e44_timing_diagnosis/report.md) |
| 只计算学生用到的边时如何选择 | STL-10 M4096 上，仅聚合者重建比显式 Demand 少 20.37% 字节，11/12 格通过耗时门槛。相对全图 D，强非 IID 6/6 格达到省时门槛，3/6 格同时更省字节。各端重建比显式版少 48.20% 字节，完整头部增时 5.19%–10.54%。 | [E58–E59](evidence/DEMAND_SCHEDULE_PROTOCOLS_20261124.md) · [协议选择](method/communication.md#按需关系协议) · [E45 历史对照](evidence/e45_on_demand_retest/report.md) |
| 当前如何选路 | 三个受测规模的固定规则 B/D/B 在 E42 的 18/18 格达到关系生成判据。E41 的拟合表在大图出现错选，短校准在正式阶段零触发。 | [E42 逐格](evidence/e42_confirmation/cells.csv) · [E41 开发](evidence/EXACT_ROUTING_BOUNDARY_20261120.md) |
| 省算的代价 | E41 的 D 在 4096 档持久认证数组约 6.29 MiB，在 16384 档约 24.85 MiB。通信编码收益来自全量和差分择短发送，同配置 B/E/D 传输字节相同。 | [E41 原始摘要](evidence/e41_routing/runs.csv) · [通信方法](method/communication.md) |
| 聚类退化如何处理 | 当前 STL-10 快照协议使用中心初始化、私有伪簇频数校正、全程私有保护和受限公共更新。受测快照能缓解严重集中，实际簇占用继续按端监测。 | [稳定性](method/stability.md) · [E38](evidence/SNAPSHOT_EXTERNAL_COMPARISON_20261118.md) |
| 部署覆盖到了哪里 | 临时聚合者的状态交接有独立恢复回放。主训练证据使用固定聚合者和可靠内存交付。 | [交接与恢复](method/aggregation_recovery.md) |

[方法](METHOD.md) · [实验总台账](evidence/EXPERIMENT_INDEX.md) · [代码与复现](REPRODUCIBILITY.md) · [待做实验](NEXT_EXPERIMENTS.md)
