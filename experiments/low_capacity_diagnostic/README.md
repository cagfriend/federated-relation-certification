# 低容量客户端稳定性诊断

按GitHub最新执行方案：4条40轮baseline验证＋8条200轮诊断，仅B。复用数量异构strong的既有缓存，无需重新训练AE或下载数据。[冻结协议](PREREGISTRATION.md)。

在仓库根目录、插电后运行：

```powershell
D:\anaconda\python.exe -m experiments.low_capacity_diagnostic.run --preset full
```

中断续跑同命令加`--resume`。默认读取`experiments/quantity_heterogeneity/results_full`及其原机缓存；前4条baseline必须匹配旧40轮轨迹，才继续private-only和公共LR0.0125两分支。全部长程仍200轮，测试每20轮。正式结果在本包`results_full/`。

重点看`report.md`、`recovery.csv`、`stages.csv`、`stage_display.csv`、`losses_and_deltas.csv`、`test_checkpoints.csv`和各runs原始JSON。历史新增观测字段缺失时保留NA；原有历史测试指标单独保留。基线短回放不用于声称160–200轮的新机制观测。

每轮T0/T1/T2只读记录，private-only不执行公共梯度更新；诊断开销单列，不产出认证省时结论。恢复仅指160/180/200各客户端均解除单簇/最大簇≥99%，不要求ACC提高，不直接称健康聚类。

开发验证：

```powershell
python -m unittest experiments.low_capacity_diagnostic.test_run -v
python -m experiments.low_capacity_diagnostic.run --preset smoke --output runs/low_capacity_smoke
```

smoke为合成小例，无科学性能/质量结论；旧代码、真实缓存和原结果保持不变。正式训练由用户启动。
