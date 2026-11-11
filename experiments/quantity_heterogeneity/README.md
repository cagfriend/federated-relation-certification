# 私有数据数量不均实验

固定N6、总私有2400张、公共有效LR0.05，比较equal/moderate/strong三档。54次主运行，`--memory-audit`另加6次strong档隔离内存回放。两种模型宽度各包含相同容量分布，不改变等权聚合。见[预注册](PREREGISTRATION.md)。

在仓库根目录、插电后运行：

```powershell
D:\anaconda\python.exe -m experiments.quantity_heterogeneity.run --preset full --prepare-device cuda --memory-audit
```

equal强制复用本机已完成的`experiments/lr_client_scaling/results_full_fixed_per_client`输入与轨迹锚点；其计时重新测。非等量档需要12份新AE/特征/KMeans准备，公共数据沿用既有STL-10目录，控制台会显示逐份进度。准备缓存不上传，异机不能直接用原绝对路径resume。

中断续跑同命令加`--resume`。首次数据不存在时显式加`--download`。完成后看本包结果目录的`report.md`、`paired_cost.csv`、`paired_summary.csv`、`private_capacities.csv`、`quality_guardrails.csv`和`memory.csv`。完整头与准备成本分列，质量只作严重退化护栏。

开发检查：

```powershell
python -m unittest experiments.quantity_heterogeneity.test_run -v
python -m experiments.quantity_heterogeneity.run --preset smoke --memory-audit --output runs/quantity_smoke
```

合成smoke不是正式性能证据。旧实验源码、P3缓存与结果均保持原样；新数量划分在隔离目录准备。
