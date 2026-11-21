# 实验代码导航

当前浮点 D 从[生成入口](public_scaling/generation.py)进入。[数值对照](../snapshot_routing/bias_numerical/README.md) · [资源对照](../snapshot_routing/bias_resources/README.md)

## STL-10 快照协议与选路

- [E38 快照外部比较](snapshot_external_comparison/README.md)提供学习协议及快照来源。
- [E39 固定路径计时](snapshot_certification_timing/README.md)核对同轨迹 B/E/D。
- [E40 公共规模对照](snapshot_graph_scaling/README.md)生成 E41 所需的审计和公共库。
- [E41 本地选路](../snapshot_routing/README.md)重放 E40 教师轨迹，比较固定路径、静态表和短校准入口。
- [E42 独立种子确认](../snapshot_routing/confirmation/README.md)生成三档的新种子轨迹并配对重放。
- [E43 完整头部训练](../snapshot_routing/full_training/README.md)复用 E42 输入，在 M=4096 上运行完整 B/E/D 训练。

全部配置、验证目标、结果、失败与异常处理见[实验台账](../docs/evidence/EXPERIMENT_INDEX.md)。实际源码清单及每文件Git blob SHA见[代码历史](../docs/evidence/CODE_HISTORY.md)。

## 运行前先确认

1. 在仓库根目录运行`python -m experiments.<package>.run`，否则可能找不到experiments。
2. 包内有README不等于仍有run.py；早期驱动应用户要求已清理，请以源码台账为准。
3. 数据、编码器和准备特征缓存未上传，原机结果中的绝对路径不是新克隆可用路径。
4. 各冻结实验复用核心和上游缓存，不能随意移动源码、改版本或跳过锚点。
5. smoke只验证实现，正式运行按原预注册。不要对旧结果目录覆盖执行。

## 当前核心

- [public_scaling](public_scaling/README.md)：保留的自包含真实训练核心，含认证/编码/协议/头部。
- [public_budget](public_budget/README.md)：固定公共学生预算。
- [private_workload](private_workload/README.md)：私有头部样本预算。
- [stl10_transfer](stl10_transfer/README.md)及后续STL-10包：复用上述核心，依赖各自准备/锚点。
- [aggregator_recovery](aggregator_recovery/README.md)：独立合成关系协议，不是模型训练恢复。
- [snapshot_external_comparison](snapshot_external_comparison/README.md)：STL-10 最新快照版与三种外部方法的 200 轮对照，以及间隔保护开销。包含正式结果与逐轮记录。

其余包逐项列在完整台账，源目录不重新分组移动。[lr_compute](lr_compute/README.md)与[lr_repeat](lr_repeat/README.md)执行包、正式结果和审核已发布；详见[发布与复查说明](../docs/evidence/LOCAL_FOLLOWUPS.md)。旧开发验证记录不代表当前正式完成状态。


## P3固定每客户端规模已完成

[lr_client_scaling](lr_client_scaling/README.md)显式使用公共有效LR0.05，仅fixed_per_client；54主+12内存已审核。原client_scaling默认仍为旧0.1，不以旧命令重现新协议。[审核](../outputs/lr_client_scaling_results_20261110/REVIEW.md)


## 私有数量不均已完成

[quantity_heterogeneity](quantity_heterogeneity/README.md)：固定N6/总2400/公共LR0.05的三容量档，54主+6内存，equal旧P3锚点18方法一致。严重退化8/18，按[正式审核](../outputs/quantity_heterogeneity_results_20261111/REVIEW.md)限定学习范围；旧代码/旧结果不改。


## 低容量稳定性诊断已完成

[low_capacity_diagnostic](low_capacity_diagnostic/README.md)：复用quantity strong缓存，4短回放+8长诊断，T0/T1/T2只读；private-only/low_lr各4/4解除严重退化。不是认证测速。[审核](../outputs/low_capacity_diagnostic_results_20261112/REVIEW.md)


## 局部公共学习率：完成与确认

[local_public_lr](local_public_lr/README.md)已完成单配置两条200轮，局部晚期通过但早期仍坍缩。[完整审核](../outputs/local_public_lr_results_20261112/REVIEW.md)。下一执行为`local_public_lr_confirmation`剩余3配置，用户启动正式运行。


## 局部LR剩余三配置确认：代码就绪

[local_public_lr_confirmation](local_public_lr_confirmation/README.md)：仅3条200轮B局部干预，复用已有缓存、完整参照清单及原引擎；新增完整基线数为0，探索case不并入确认分母。主AI开发验证通过，独立复审因子代理额度限制待补，正式由用户启动。


## 局部LR三配置确认已完成，E29

局部公共LR剩余三配置确认已完成：seed1001/α0.1、seed1002/IID及α0.1各200轮B；160/180/200全部6客户端检查为3/3配置、54/54项通过。此前1001/IID探索单列。早期严重集中仍存在，解除严重退化不等于充分健康聚类；本轮不使用计时或加速结论。 [报告](local_public_lr_confirmation/results_full/report.md) · [审核](../outputs/local_public_lr_confirmation_results_20261113/REVIEW.md)。下一项计算实验另行设计。


## 已完成私有校正和计算比较，E30/E31

[private_prior](private_prior/README.md)：私有伪簇频数校正四条B协作轨迹全部通过：两个小客户端最后40轮平均同簇边由63.4%–82.5%降至17.9%–22.9%，末轮测试最大簇为23.2%–37.6%。保持既定学习率和更新预算，早期7–11轮高度集中仍存在，结论为两个既有seed的探索性证据。

[private_prior_compute](private_prior_compute/README.md)：私有校正后的四环境B/E/D共12次主运行及6次隔离内存回放完成，关系/参数/质量精确一致，117,964,800次关系与157,286,400次候选检查零错误。D/B完整头部省35.25%–43.00%，D/E省10.31%–14.12%；通信字节相同，两个内存配置D/B峰值增加约14.5%。每环境每方法一次。

后续新seed联合确认仍待另行设计与实现。



## E32新种子确认已完成

新seed1201/1202/1203 × 两划分 × B/E/D各3次重复，共54次独立进程完成。IID完整头部D/B、D/E中位省时39.08%/16.67%，强非IID为39.29%/12.45%；预定性能及质量条件全部通过，逐轮匹配各case全量B参考。 [执行包](private_prior_confirmation/README.md) · [审核](../outputs/private_prior_confirmation_review/REVIEW.md)
