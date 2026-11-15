# 新种子下的质量与省时联合确认

先在工作区根目录启动。程序复用现有STL-10原始数据，为6个新seed/划分组合准备AE及冻结特征，再运行54次独立进程。每方法每环境200轮，单线程、串行。

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.private_prior_confirmation.run --preset full --prepare-device cuda
```

中断后使用同一命令加 --resume。准备阶段中断的非完整缓存会保留并明确报错，必要时指定新的 --cache 目录。本机原始数据已存在，通常无需 --download。

全部54次通过精确轨迹检查后显示Finished，并写入results_full/finished.json。结果含report.md、decision.json、raw_runs.csv、seed_pairs.csv、quality.csv及逐次原始runs目录。方法顺序按三个重复轮转，统计时先平均每seed的重复，再做D/B和D/E配对。完整判据见PREREGISTRATION.md。

正式54次计时关闭全量oracle和公共/私有探针，使用每case首次B的完整教师关系作为精确参照。小规模测试启用oracle，检查认证结果并对照前序引擎。每20轮测试评估在计时外保留。既有数据、正式结果和当前共享训练核心已保留，旧已发布驱动可通过outputs/confirmation_cleanup/removed_published_source.zip或GitHub原提交恢复。

小规模验证如下。

```powershell
D:\anaconda\python.exe -m pytest experiments/private_prior_confirmation -q --tb=short
D:\anaconda\python.exe -m experiments.private_prior_confirmation.run --preset smoke
```


## 正式完成状态，2026-11-14

新seed1201/1202/1203 × 两划分 × B/E/D各3次重复，共54次独立进程完成。IID完整头部D/B、D/E中位省时39.08%/16.67%，强非IID为39.29%/12.45%；预定性能及质量条件全部通过，逐轮匹配各case全量B参考。 [正式复核](../../outputs/private_prior_confirmation_review/REVIEW.md)。开发记录按记录时间解释。原始大JSON见[无损归档](../../archives/private_prior_confirmation_20261114.manifest.json)，恢复可校验完成清单。本机绝对路径仅作来源记录，异机需重新准备。
