# 实验代码导航

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

其余包逐项列在完整台账，源目录不重新分组移动。[lr_compute](lr_compute/README.md)与[lr_repeat](lr_repeat/README.md)执行包、正式结果和审核已发布；详见[发布与复查说明](../docs/evidence/LOCAL_FOLLOWUPS.md)。旧开发验证记录不代表当前正式完成状态。


## P3固定每客户端规模已完成

[lr_client_scaling](lr_client_scaling/README.md)显式使用公共有效LR0.05，仅fixed_per_client；54主+12内存已审核。原client_scaling默认仍为旧0.1，不以旧命令重现新协议。[审核](../outputs/lr_client_scaling_results_20261110/REVIEW.md)


## 私有数量不均已完成

[quantity_heterogeneity](quantity_heterogeneity/README.md)：固定N6/总2400/公共LR0.05的三容量档，54主+6内存，equal旧P3锚点18方法一致。严重退化8/18，按[正式审核](../outputs/quantity_heterogeneity_results_20261111/REVIEW.md)限定学习范围；旧代码/旧结果不改。
