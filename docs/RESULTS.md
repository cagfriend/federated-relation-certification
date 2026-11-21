# 研究结论与适用边界

这个项目在公共无标签样本图上交换硬关系。B 全量计算，E 认证样本标签，D 直接认证关系。三条路径在受测的同配置轨迹上提交相同的硬关系和聚合目标。计算贡献以精确关系生成和完整头部的耗时为主，聚类质量用于确认受测训练处于可用范围。

| 研究问题 | 当前结论 | 证据 |
|---|---|---|
| D 什么时候节省关系生成时间 | E42 的 4096 档六个配置均比 B 和 E 快，分别节省 12.34%–31.69% 和 11.86%–23.81%。 | [E42 配对](evidence/e42_confirmation/comparisons.csv) |
| 关系生成收益能否兑现到完整头部 | E43 的 4096 档，IID 中 D/B 有 3/3 格达标，完整头部省 8.18%–10.57%。D/E 有 2/3 格达标。强非 IID 中两项均为 0/3。 | [E43 完整报告](evidence/e43_full_training/report.md) |
| 强非 IID 的差异是否持续 | E44 的两个受测配置相对 B 分别省 5.16% 和 4.94%，未检出持续的非生成额外耗时。 | [E44 分阶段](evidence/e44_timing_diagnosis/report.md) |
| 只计算学生用到的边时如何选择 | E45 的 IID 配置 D 最快。强非 IID 中 Demand 比 D 省 10.56% 完整头部时间。当前显式按需协议累计字节增加，两格共享一个种子。 | [E45 合并结果](evidence/e45_on_demand_retest/report.md) |
| 当前如何选路 | 三个受测规模的固定规则 B/D/B 在 E42 的 18/18 格达到关系生成判据。E41 的拟合表在大图出现错选，短校准在正式阶段零触发。 | [E42 逐格](evidence/e42_confirmation/cells.csv) · [E41 开发](evidence/EXACT_ROUTING_BOUNDARY_20261120.md) |
| 省算的代价 | E41 的 D 在 4096 档持久认证数组约 6.29 MiB，在 16384 档约 24.85 MiB。通信编码收益来自全量和差分择短发送，同配置 B/E/D 传输字节相同。 | [E41 原始摘要](evidence/e41_routing/runs.csv) · [通信方法](method/communication.md) |
| 聚类退化如何处理 | 当前 STL-10 快照协议使用中心初始化、私有伪簇频数校正、全程私有保护和受限公共更新。受测快照能缓解严重集中，实际簇占用继续按端监测。 | [稳定性](method/stability.md) · [E38](evidence/SNAPSHOT_EXTERNAL_COMPARISON_20261118.md) |
| 部署覆盖到了哪里 | 临时聚合者的状态交接有独立恢复回放。主训练证据使用固定聚合者和可靠内存交付。 | [交接与恢复](method/aggregation_recovery.md) |

[方法](METHOD.md) · [实验总台账](evidence/EXPERIMENT_INDEX.md) · [代码与复现](REPRODUCIBILITY.md) · [待做实验](NEXT_EXPERIMENTS.md)
