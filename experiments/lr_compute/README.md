# P1，0.05下的B/E/D资源实验

公共2步、公共有效学习率0.05、私有学习率0.1。复用学习率确认的8个配置、编码器、特征和伪标签。每配置B/E/D各运行200轮，共24次；随后执行6次关闭oracle与评估的隔离内存回放。

输入固定为 `experiments/public_lr_confirmation/results_full/`。每个方法的参数与质量需要匹配已有0.05诊断轨迹，三元组关系、目标、参数和通信逐轮一致。具体矩阵、成本口径及质量判据见[PREREGISTRATION.md](PREREGISTRATION.md)。

插电并关闭自动休眠，从工作区根目录执行。

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.lr_compute.run --preset full
```

先核验输入与历史完成清单，之后输出Running，最后是Memory。结果保存在 `experiments/lr_compute/results_full/`，结束显示Finished。此次读取已完成缓存。

中断后续跑。

```powershell
D:\anaconda\python.exe -m experiments.lr_compute.run --preset full --resume
```

先看report.md、paired_cost.csv的每配置D/B、D/E完整头部和生成耗时，再看持久数组、隔离内存峰值、通信及质量记录。本轮每方法一次，重复性能确认属于下一阶段。

K64/强非IID/1002旧准备阶段的休眠污染继续按原记录处理，含该新增准备成本的总量与比值为NA。新头部训练与生成时间正常保留。

开发检查。

```powershell
D:\anaconda\python.exe -m unittest experiments.lr_compute.test_run
D:\anaconda\python.exe -m experiments.lr_compute.run --preset smoke --source-results outputs/public_lr_confirmation_review_20261106/smoke_final
```

开发smoke复用上轮合成输入与0.05锚点，12次方法运行加6次内存回放，每条12轮。
