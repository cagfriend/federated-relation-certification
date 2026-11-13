# 私有伪簇频数校正

在工作区根目录的 PowerShell 启动四条正式 B 协作轨迹。

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.private_prior.run --preset full
```

中断后使用同一命令加 `--resume`。结果写入 `experiments/private_prior/results_full`。完成标志为 `finished.json`，报告为 `report.md`，配对结果为 `paired.csv`，六端逐轮轨迹为 `curves.csv`，逐端测试指标为 `quality.csv`。完整原始记录位于 `runs`。正式运行依赖本机 E28/E29 历史结果及其准备缓存。

小规模验证命令如下。

```powershell
D:\anaconda\python.exe -m pytest experiments/private_prior/test_private_prior.py -q
D:\anaconda\python.exe -m experiments.private_prior.run --preset smoke --output experiments/private_prior/validation_example
```

实现复用既有 E28 引擎快照，仅替换私有更新函数导入，并将探针和设计导入指向原模块。原引擎及历史源码保持封存，避免历史来源校验失效。测试逐行比对该快照来源。修改细节与正式通过标准见 PREREGISTRATION.md。


正式结果已完成并审核。[结果复核](../../outputs/private_prior_results_review/REVIEW.md)。原始大JSON及CSV以无损ZIP保存，恢复方式见[归档清单](../../archives/private_prior_20261113.manifest.json)。本机已有完整原文件；异机需要按清单恢复并重新准备缓存。
