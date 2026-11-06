# 公共学习率0.05初步确认

测试N12/K10和N6/K64两类场景，均保留公共2步，配对比较公共有效学习率0.1与0.05。私有学习率0.1。

每类覆盖健康种子、已知失败种子和新seed1101的IID/强非IID两划分，共8个配置。复用5份既有记录，新增11条200轮B轨迹。准备数据和训练入口复用已有实现。具体矩阵和操作判据见[PREREGISTRATION.md](PREREGISTRATION.md)。

插电并关闭自动休眠，在工作区根目录运行。

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.public_lr_confirmation.run --preset full --prepare-device cuda
```

新seed首次需要准备独立编码器、特征和伪标签。准备缓存位于本实验目录，占用数GB至十余GB空间。控制台先显示Preparing，之后显示Historical或Running。结果保存到 `experiments/public_lr_confirmation/results_full/`，结束显示Finished。

```powershell
D:\anaconda\python.exe -m experiments.public_lr_confirmation.run --preset full --resume
```

续跑校验已完成记录、冻结代码与输入身份，未完成轨迹重新运行。若中断发生在新缓存准备中，原准备器会指出未完成缓存路径；检查并移出该未完成目录后再续跑。完整缓存与历史结果保留。

优先查看report.md和verdicts.csv的逐配置结构、过程、NMI地板与适用的ACC副作用护栏。clients.csv包含逐客户端检查点和来源。records中的JSON保存逐轮目标、参数摘要、边顺序和新轨迹的阶段探针，源于历史的记录另存来源路径与SHA256。

本轮检验退化和质量边界，阶段计时包含探针。资源收益在候选确认后进行同配置B/E/D对照。

开发smoke使用合成STL格式、两种K的实际加载路径、两划分和12轮，共8次新运行。

```powershell
D:\anaconda\python.exe -m unittest experiments.public_lr_confirmation.test_run
D:\anaconda\python.exe -m experiments.public_lr_confirmation.run --preset smoke
```
