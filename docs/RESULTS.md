# 研究结论与适用边界

这个项目在公共无标签样本图上交换硬关系。B 全量计算，E 认证样本标签，D 直接认证关系。三条路径在受测的同配置轨迹上提交相同的硬关系和聚合目标。计算贡献以精确关系生成和完整头部的耗时为主，聚类质量用于确认受测训练处于可用范围。

| 研究问题 | 当前结论 | 证据 |
|---|---|---|
| D 什么时候节省关系生成时间 | E41 的 STL-10 匹配图中，M=4096 的四个配置均快于 B 和 E，分别节省 10.02%–26.29% 和 16.89%–19.47%。M=512、16384 的四个配置均由固定 B 最快。 | [E41 审阅](evidence/EXACT_ROUTING_BOUNDARY_20261120.md) |
| 关系生成收益能否兑现到完整头部 | E40 的 4096 档在复测替换的敏感性口径下，D 对 B 有 3/4 格、对 E 有 2/4 格达到配对门槛。E41 测量同轨迹生成重放。 | [E39/E40 审阅](evidence/SNAPSHOT_CERTIFICATION_SCALING_20261119.md) |
| 当前如何选路 | 按规模和头宽拟合的 S 在中图有 3/4 格相对 B 达标，大图四格均有平均退化。C 的回本门槛使正式试跑为零。三个受测规模上可冻结 B/D/B 作为下一轮候选。 | [E41 明细](evidence/e41_routing/boundaries.csv) · [待做](NEXT_EXPERIMENTS.md) |
| 省算的代价 | E41 的 D 在 4096 档持久认证数组约 6.29 MiB，在 16384 档约 24.85 MiB。通信编码收益来自全量和差分择短发送，同配置 B/E/D 传输字节相同。 | [E41 原始摘要](evidence/e41_routing/runs.csv) · [通信方法](method/communication.md) |
| 聚类退化如何处理 | 当前 STL-10 快照协议使用中心初始化、私有伪簇频数校正、全程私有保护和受限公共更新。受测快照能缓解严重集中，实际簇占用继续按端监测。 | [稳定性](method/stability.md) · [E38](evidence/SNAPSHOT_EXTERNAL_COMPARISON_20261118.md) |
| 部署覆盖到了哪里 | 临时聚合者的状态交接有独立恢复回放。主训练证据使用固定聚合者和可靠内存交付。 | [交接与恢复](method/aggregation_recovery.md) |

[方法](METHOD.md) · [实验总台账](evidence/EXPERIMENT_INDEX.md) · [代码与复现](REPRODUCIBILITY.md) · [待做实验](NEXT_EXPERIMENTS.md)
