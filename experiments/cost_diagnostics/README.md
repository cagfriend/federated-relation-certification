# E/D关系生成成本分解

本实验解释现有稀疏/密图结果，不实现自适应选择。训练核心 `public_scaling/*.py` 和上次图密度正式结果均不修改。

## 固定设计

正式配置直接读取 `experiments/graph_density/results_graph`：公共库4096、degree 1/4/8、六客户端宽512×3/2048×3、K10、200轮、seeds404/505/606。复用已核验的私有准备缓存，不重做编码器。没有训练数据标签参与训练。

每个配置/seed只重走一条真实E训练轨迹，共9条；每轮的教师快照额外送入四套独立缓存：未插桩E、插桩E、未插桩D、插桩D。四条求值路径轮换执行顺序，消费相同快照；每条路径按自身刷新历史演进。不会把E缓存交给D，或者将D缓存从历史重新拼接。

每轮要求：重走的E模型摘要、通信、评估与上次保存结果一致；四条求值路径的关系都等于全量oracle；同方法插桩/未插桩的缓存逐数组一致；重算数量、候选条目数及认证边数等于上次同方法记录。不一致立即停止。

## 分解项目

| 字段 | 包含内容 |
|---|---|
| advance | 参数变化界、前缀预算与上次教师参数更新 |
| candidates | 候选矩阵、保守数值保护 |
| bitsets | D的位集合与单元素判断；E不做这项工作 |
| certification | E的候选大小/单元素及边可知判断；D的交集/同单元素关系判断 |
| endpoints | 重算端点收集、去重掩码与索引 |
| teacher | 重算特征索引、矩阵乘、有限值检查与argmax |
| cache | 间隔、预测赢家和引用预算更新 |
| finalize | 最终关系生成/检查及原有统计组装 |

计时直接在原函数AST上插入上下文管理器，不复制修改认证公式；自动剥除计时包装后必须与原始AST完全一致，否则拒绝启动。原认证数值保护仍是工程性保护，不因AST检查变成浮点形式化证明。

首次全量初始化不混入上述每轮阶段，单独保留bootstrap记录。额外计数采集放在阶段计时之后；D另记未认证边的端点并集大小（包含其中已经单元素的端点）和实际刷新端点数。

## 运行

使用原机器/原环境，已有原始数据、准备缓存和正式图密度结果：

```powershell
Set-Location -LiteralPath 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
& 'D:\anaconda\python.exe' -m experiments.cost_diagnostics.run --check-only
& 'D:\anaconda\python.exe' -m experiments.cost_diagnostics.run
```

默认输出 `experiments/cost_diagnostics/results_full`。只检查命令不启动训练、不写结果。程序验证来源清单、缓存资产及case载荷后才重走训练。

恢复：

```powershell
& 'D:\anaconda\python.exe' -m experiments.cost_diagnostics.run --resume
```

完整case不重跑；中断的case从第1轮重走。来源完成清单或本诊断代码改变时拒绝恢复。输出目录不得覆盖或嵌入来源目录。

缩小的真实数据路径验证（3轮、公共样本32、两客户端宽32/64；不是正式性能结论）：

```powershell
& 'D:\anaconda\python.exe' -m experiments.cost_diagnostics.run --preset smoke
```

它复用前一步留下的 `experiments/graph_density/validation_smoke_20261030`。新机器无准备缓存不能直接使用历史来源；本入口没有跨机迁移/重准备功能。

## 结果与解释

- `summary.csv`：每配置/seed/方法的阶段总耗时、未分段耗时、控制与插桩墙钟、重算端点数量及D未认证端点并集数量，均排除bootstrap；初始化单列。
- `summary.json`、`report.md`：各seed汇总之后的中位数，各方法分别描述，不把方法耗时中位数相除冒充配对加速。
- 各case JSON：逐轮逐客户端的阶段计时、未分段耗时和原统计。
- `environment.json`、`completed.json`：诊断代码版本、来源完成清单摘要与输出校验。

控制组用于观察插桩前后墙钟差异；它仍处在诊断运行的CPU缓存/额外工作负载下，不能替代上一轮正式未插桩性能实验。阶段和为原始阶段计时；墙钟减阶段和的差值含计时器、上下文管理器、计数采集和未分段操作，不能全称为纯计时器开销，也不做差值校正。

这里不报告完整训练加速、不测网络或内存峰值。若发现便宜且稳定的E/D判定依据，再单独设计规则、新种子验证和真正净收益对照；当前不根据诊断结果现场挑选更快路径。
