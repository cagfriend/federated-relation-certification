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

其余包逐项列在完整台账，源目录不重新分组移动。`lr_compute`和`lr_repeat`本地后续状态见[专门说明](../docs/evidence/LOCAL_FOLLOWUPS.md)，本次没有发布其执行包。
