# STL-10退化定位

方案：`outputs/stl10_transfer_results_20261101/DIAGNOSTIC_PLAN.md`。本包只做已有缓存的只读体检，以及P仅私有、J原联合、F固定第1轮教师目标三条轨迹。正式配置为seed1001、IID、M16384、40轮，复用STL-10原准备和全部超参数，不训练编码器，不下载数据，不改旧源码或结果。

J必须匹配此前B的前40轮；F第1轮必须与J相同，后续学生仍执行新鲜前向。P生成的关系/目标仅用于反事实诊断，不执行公共SGD。F日志中的动态教师计数并不是学生实际消费的目标：实际目标见`student_targets`和`fixed_round1_targets.npy`。

在工作区根目录执行：

```powershell
cd "C:\Users\tjp\Documents\Codex\2026-10-14\new-chat"
D:\anaconda\python.exe -m experiments.stl10_diagnostics.run
```

输出`experiments/stl10_diagnostics/results_full/`，完成时显示`Finished`并写`completed.json`。默认不覆盖已有目录；中断后用新的`--output`完整重跑这次短程诊断。无需重新准备特征。首次只读检查、完整测试评估和特征加载可能暂时没有逐轮输出。

小规模合成夹具：

```powershell
D:\anaconda\python.exe -m experiments.stl10_diagnostics.run --preset smoke
```

默认读取`stl10_transfer/results_smoke_final`，夹具只验证流程。可用`--source-results`显式选择同类型已完成来源，不可混用真实与夹具。

主要文件：`initial_inspection.json`记录特征、伪标签、最近中心与随机头的体检；`P/J/F.json`记录每轮三个阶段、固定1024公共探针、检查点完整测试评估、固定批次梯度和目标分布；`report.md`展示各分支检查点的簇占用与ACC。固定批次梯度不是整个epoch梯度；计时含额外诊断，不作省时比较。

`stages.csv`、`gradients.csv`可直接查看逐客户端数值；`public_cluster_concentration.svg`展示各客户端三分支的公共探针集中程度。P曲线取私有更新后，J/F取公共更新后。所有观察均不改变训练；小规模回归测试核对开启/关闭诊断时参数与损失一致。

真实标签只用于测试评估；伪标签拟合准确率另命名，不等同于测试ACC。实际随机头由原`Head`初始化，KMeans中心只用于额外只读探针。详见方案的判断表；本轮目标是定位退化阶段，不要求ACC提高。
