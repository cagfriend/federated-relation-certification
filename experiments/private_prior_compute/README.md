# 私有校正后的计算对照

在工作区根目录启动12次B/E/D主运行及6次隔离内存回放。

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.private_prior_compute.run --preset full --memory-audit
```

中断后在同一命令末尾加 --resume。程序显示Finished且results_full/finished.json存在时，主运行与内存回放均已完成。默认结果位于experiments/private_prior_compute/results_full，其中report.md为摘要，comparisons.csv含逐方法阶段及头部配对省时，runs/和memory/保留原始逐轮记录。原始traffic字段保留实际协议通信统计。

输入直接复用已完成private_prior的四条轨迹及准备缓存。正式实验没有新增AE预训练。代码不改变历史private_prior，新的引擎从其快照扩展方法选择与计时外oracle审计。完整配置及口径见PREREGISTRATION.md。

小规模验证命令如下。

```powershell
D:\anaconda\python.exe -m pytest experiments/private_prior_compute/test_compute.py -q --tb=short
D:\anaconda\python.exe -m experiments.private_prior_compute.run --preset smoke --memory-audit
```


正式结果已完成并审核。[结果复核](../../outputs/private_prior_compute_results_review/REVIEW.md)。原始大JSON及CSV以无损ZIP保存，恢复方式见[归档清单](../../archives/private_prior_compute_20261113.manifest.json)。本机已有完整原文件；异机需要按清单恢复并重新准备缓存。
