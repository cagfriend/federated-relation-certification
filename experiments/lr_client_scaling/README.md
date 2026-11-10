# P3：固定每客户端400张，公共学习率0.05

与旧fixed_total结果分开；新包只允许fixed_per_client。18配置×B/E/D=54次独立进程，`--memory-audit`增加12次内存回放。旧实验不修改。详细口径见[预注册](PREREGISTRATION.md)。

在仓库根目录、插电后运行：

```powershell
D:\anaconda\python.exe -m experiments.lr_client_scaling.run --preset full --prepare-device cuda --memory-audit
```

STL-10文件复用`experiments/stl10_transfer/data`，本轮通常需要18份新私有准备（AE/特征/KMeans），会逐份显示进度；不需要重新下载已校验数据。缺少数据时显式加`--download`。准备可能比头部训练更耗时，尚不估计正式墙钟。

中断续跑同命令加`--resume`。准备中断导致不完整缓存时按报错路径处理，不能把旧fixed_total缓存当成400张输入。完成结果在本包`results_full_fixed_per_client/`；看`report.md`、`paired_cost.csv`、`paired_summary.csv`、`quality_guardrails.csv`及`memory.csv`。不自动删离群值，不要求ACC提升；所有严重退化或D/E负收益配置保留。

开发检查：

```powershell
python -m unittest experiments.lr_client_scaling.test_run -v
python -m experiments.lr_client_scaling.run --preset smoke --memory-audit --output runs/p3_smoke
```

smoke为合成小实例。主训练串行，不能把总耗时/N当成并行轮时延。准备缓存不上传；旧结果的本机路径不能直接用于异机resume。正式进程由用户启动。
