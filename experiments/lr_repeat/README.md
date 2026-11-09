# P2固定配置重复计时

固定4个强非IID配置，N12/K10的seed1001、1101，以及N6/K64的seed1002、1101。每配置B/E/D各3次，共36次独立进程运行。公共学习率0.05、公共2步、私有学习率0.1、200轮，复用P1全部缓存。

每配置的三次重复顺序为BED、EDB、DBE，平衡方法位置。所有重复都匹配P1同方法逐轮参数和方法专属计数。每配置单列三次配对比值，按[C1/C2/C3冻结规则](PREREGISTRATION.md)机械判定。

插电并关闭自动休眠，从工作区根目录运行。

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.lr_repeat.run --preset full
```

先显示Checking并核验P1清单与方法锚点，随后Running。结果位于 `experiments/lr_repeat/results_full/`，完成显示Finished。此次直接读取现有特征与伪标签缓存。

中断后续跑。

```powershell
D:\anaconda\python.exe -m experiments.lr_repeat.run --preset full --resume
```

完整单次运行校验后保留，未完成单次从初始头重跑。运行过程保存电源采样和起止时间，计时全部保留。

重点看report.md、paired_repeats.csv、case_summary.csv和criteria.csv。主要指标为完整头部D/B、D/E比值和省秒，生成及各阶段分列。K64/强非IID/1002的历史污染准备成本仍按NA处理，训练计时保留。进程峰值包含审计与评估，隔离内存证据沿用P1。

开发检查使用P1已完成的合成smoke输入与方法锚点，两配置×三方法×三重复，共18次12轮运行。

```powershell
D:\anaconda\python.exe -m unittest experiments.lr_repeat.test_run
D:\anaconda\python.exe -m experiments.lr_repeat.run --preset smoke --source-results outputs/lr_compute_review_20261106/smoke_v2
```
