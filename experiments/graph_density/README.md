# 固定公共库的图密度实验

本阶段只改变固定公共样本上的关系图密度。沿用已经验证的 `public_scaling` 训练核心，不改变认证、编码、聚合、教师快照时序或学生梯度更新，也不修改该目录的 Python 源码。专用入口负责运行前检查、复用已完成组和补充图密度诊断。

## 冻结设计

| 项目 | 配置 |
|---|---|
| 数据 | Fashion-MNIST；公共候选池16384，实际公共库4096，固定私有集43616 |
| 图度数 | 1 / 4 / 8，无向、无自环、无重边、每点度精确；低度图嵌套在高度图中 |
| 边数 | 2048 / 8192 / 16384 |
| 每客户端每轮公共SGD步数 | 8 / 32 / 64，边batch256，每轮完整公共图1 epoch |
| 客户端 | 6个；MLP宽度512×3、2048×3；编码器冻结，训练线性头 |
| 固定项 | 每seed的私有数据、全部公共样本、AE、伪标签、头初态、学习率0.1、10簇 |
| 方法 | B全量 / E逐样本认证 / D关系认证；完全相同的自适应编码和聚合 |
| 重复 | seeds=404/505/606，每组200轮，保留全部逐轮oracle审计与模型摘要检查 |

主要问题：边数变多时，D相对B和E是否仍有净收益；认证通过比例、候选集、重算端点并集与边检查成本怎样变化。固定M下B只对每个公共样本做一次教师前向，不会因多了边而重复前向。不得预设密图一定使优化更显著。

## 运行

PowerShell，从工作区启动。正式入口默认复用上次完成的 `results_public` 中三个degree=1 case，复制前校验，不重跑它们；新增degree=4/8共18次方法训练。源码与依赖必须保持与上次一致。

```powershell
Set-Location -LiteralPath 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
& 'D:\anaconda\python.exe' -m experiments.graph_density.run --check-only
& 'D:\anaconda\python.exe' -m experiments.graph_density.run
```

默认输出 `experiments/graph_density/results_graph`。不覆盖旧结果；默认对degree=8做9次隔离内存回放，回放不纳入性能计时。若需要三个degree都有独立进程峰值测量，首次运行使用：

```powershell
& 'D:\anaconda\python.exe' -m experiments.graph_density.run --memory-scope all
```

这会做27次内存回放。两条正式命令选择一条即可。若已开始或中断，不要重新换参数覆盖目录，用：

```powershell
& 'D:\anaconda\python.exe' -m experiments.graph_density.run --resume
```

恢复使用已保存的内存选项；已完成case不重跑，未完成case从第1轮重跑。入口固定复用本轮CUDA准备缓存；不重做AE。它不支持随意更换种子/轮数/CPU准备设备，这些属于另一项实验。

## 重点比较与判定

1. 主指标：各degree内、同seed配对的D/B与D/E完整头训练耗时比、绝对省时、胜出种子数。计入初始化；负收益也完整报告，不按结果删组。
2. 机制指标：关系生成耗时、教师实际重算端点/比例、认证边比例、平均候选集大小；同时看私有、公共、交换阶段，避免把其波动误归为认证收益。
3. 资源指标：方法持久数组与独立内存回放；通信字节用于验证相同编码下B/E/D一致，不把认证描述为额外消息压缩。
4. 正确性：每轮关系/计数/接收目标等于全量oracle，B/E/D头摘要、消息与已保存评估一致。当前重点为过程保持，不据此宣称协作优于Local。

三个seed全部更快是方向一致的证据，不等同于统计显著性或所有场景有效。D/E的整体收益可能较小。若只generation获益、完整流程没有收益，应明确写出。

主要结论使用T；C0+T仍是共享最大公共池准备口径，含测试特征准备。degree增加同时增加公共学生更新预算，不能声称固定学生预算。跨degree轨迹允许不同。degree=1来自上次运行，跨degree绝对计时可能有批次环境差异，应以各degree内部的配对比较为主。

## 输出

原有 `report.md`、`paired_summary.json`、各case原始JSON与memory文件保持原格式。新增输出在子目录 `graph_analysis/`，避免改变原完成清单的根JSON：

- `report.md`：按degree的D/B、D/E配对结果。
- `diagnostics.json`：逐seed配对比值、绝对省时和中位数；先配对再汇总。
- `diagnostics.csv`：逐degree/seed/方法分阶段耗时、候选集/认证/重算统计、实际端点、正关系比例、步数、持久数组与流量。
- `implementation.json`：生成诊断时入口/分析文件的源码哈希、训练核心哈希及所分析完成记录的哈希。训练恢复冻结核心版本；新增入口/分析版本记录用于追溯，不额外限制核心恢复。

需要单独重建诊断时：

```powershell
& 'D:\anaconda\python.exe' -m experiments.graph_density.analyze --output experiments/graph_density/results_graph
```

该入口只接受完整实验，检查原始JSON校验及模型/质量/消息一致性，不重跑训练。所有计时仍为串行CPU头训练，消息在内存中交换；尚无实网、临时聚合者选举或故障恢复测试。
