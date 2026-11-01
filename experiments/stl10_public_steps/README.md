# STL-10公共更新步数干预

只将每客户端每轮公共SGD由8步改为1/2/4步，8步参照也重放。私有7步、原完整教师图（M16384、degree1）、聚合和动态目标刷新、batch256、学习率与公共损失权重保持不变。seed1001、IID、6个原客户端、40轮；无预热、无新损失、无AE/KMeans重训。各档使用同一轮公共边随机排列的不同长度前缀，公共信息消费预算会随步数改变，不称为仅改变学习率。

本轮是根据已观察到的退化做探索性修复试验，不是独立复核或正式性能确认。主要看逐客户端簇占用、公共固定探针集中度及私有伪标签拟合；ACC/NMI/ARI辅助检查，不要求超过先前数据集。额外诊断使耗时不适合作省时结论。降低公共预算的计算减少属于预算调整，不能记到关系认证名下。

```powershell
cd "C:\Users\tjp\Documents\Codex\2026-10-14\new-chat"
D:\anaconda\python.exe -m experiments.stl10_public_steps.run
```

原缓存和结果只读，结果写入本目录`results_full`。输出目录已存在时拒绝覆盖；中断后用新的`--output`重跑这次短程干预。最初会校验缓存，之后按档位和轮次输出进度。四档全部结束并核验后显示`Finished`，生成`completed.json`。

8步必须匹配旧B前40轮；各档私有样本ID、伪标签直方图、步数和随机顺序摘要必须相同，但参数、目标、损失应允许不同。三阶段观察与梯度探针直接复用已验证诊断实现，不影响参数。

输出`public_steps_1/2/4/8.json`、`checkpoints.csv`、`stages.csv`、`gradients.csv`和`public_concentration.svg`，`report.md`给出各检查点聚类状态。此轮不自动宣布某档修复成功，若只延迟塌缩而40轮未发生，还需后续长程/其他种子验证。

小规模夹具验证：

```powershell
D:\anaconda\python.exe -m experiments.stl10_public_steps.run --preset smoke
```

smoke为3轮、公共1/2/4步，原夹具64条边只够4步，不伪造8步。原锚点为1步；真实正式配置始终为1/2/4/8。Python `-O`被拒绝；本轮使用CPU头训练，无CUDA预训练要求。
