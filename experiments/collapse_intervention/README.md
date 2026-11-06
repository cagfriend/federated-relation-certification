# N12单簇与近单簇诊断

当前入口执行3条200轮B轨迹。配置固定为STL-10、N12、K10、Dirichlet α=0.1、seed1003，直接读取客户端数实验的已完成结果和缓存。

|分支|公共更新|
|---|---|
|private_only|关闭公共学生参数更新|
|public1|每客户端每轮1步|
|public2_half|每客户端每轮2步，公共有效学习率0.05|

私有学习率0.1。原2步、公共有效学习率0.1的历史B轨迹复制为参照。阶段探针、测试评估和教师关系监测用于解释集中过程。完整设计见[PREREGISTRATION.md](PREREGISTRATION.md)。

插电并关闭自动休眠，在工作区根目录运行。

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.collapse_intervention.run --preset full
```

先验证历史结果与缓存，再做原2步配置的3轮匹配预检，然后依次运行3个干预分支。复用现有准备数据。运行结束显示Finished，输出位于 `experiments/collapse_intervention/results_full/`。

中断后执行以下命令。已完成分支校验后保留，未完成分支从初始头重跑。

```powershell
D:\anaconda\python.exe -m experiments.collapse_intervention.run --preset full --resume
```

优先查看 `report.md` 和 `clients.csv` 的200轮最终与过程集中度，再查看 `stages.csv` 的after_private/after_public差别、私有拟合和公共探针。`events.csv`列出每客户端的严格单簇或≥99%集中事件，`rounds.csv`保留教师同簇边比例与训练工作量。原始JSON保存完整参数摘要、边顺序摘要和逐客户端观测。

这是已知失败种子的定位实验。结果用于选择下一阶段健康种子、新种子确认的候选。所有计时按诊断记录解读，private_only仍生成教师关系和聚合用于观察，阶段计时包含探针开销。

开发检查使用合成STL格式、4客户端、12轮。

```powershell
D:\anaconda\python.exe -m unittest experiments.collapse_intervention.test_run
D:\anaconda\python.exe -m experiments.collapse_intervention.run --preset smoke
```
