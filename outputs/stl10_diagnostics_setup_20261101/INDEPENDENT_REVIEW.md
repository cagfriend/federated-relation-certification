# Runner 独立审阅

范围：只读审阅 `experiments/stl10_diagnostics/run.py`，并检查其调用的 `probes.py` 与既有私有工作负载/公共学生更新实现；未运行实验，未改实验代码。

## 复核结论（修正后）

此前列出的四项记录/核验缺口均已补齐，`-O` 也被入口显式拒绝。关键修正与 smoke 产物相符；当前没有已知阻塞项。此结论仅验收实现和 smoke 流程，不代表真实 STL-10 诊断已运行或结论成立。

## 已核验

- `drive` 每个 arm 都新建 `WorkloadMethod('B', ...)`，因此各分支从相同的seed 310头初始化独立开始；每个客户端头部相互独立。P 的 `update` hook 返回零损失/零步且不更新头，私有 epoch 仍按既有 sampler 执行；J 调用既有 `update`；F 只在首轮复制聚合 `targets`，此后仍把当前头传给原更新函数，故每一步重新前向并训练学生。
- P 仍生成关系、聚合并做通信，但不执行公共学生更新；这会增加诊断耗时，不改变 P 的“仅私有参数更新”语义。记录将该臂目标标为反事实，`public_optimizer_steps` 置零。
- J 的 `compare_anchor` 检查相同初始头及计划列出的逐轮轨迹字段（包括参数摘要、公共调度、私有工作量、关系/通信摘要和损失）；F 与 J 首轮参数摘要和目标数组摘要相核对。F 目标另存为 NPY。
- monkeypatch 通过上下文管理器在异常时也会恢复。三个分支共用只读准备数据但有各自头和协议状态；输出目录要求为空，默认输出在新诊断目录。检查环境及原始缓存元数据，且运行前后核验旧实验环境；代码哈希覆盖诊断目录的 Python 文件。
- probe 与梯度批次使用局部 `SeedSequence`（流 610/611），既有私有/公共训练使用各自 401/402 流；probe 不调用 optimizer、不写头参数，也不使用标签训练。J 锚点对照可检出诊断观察导致的 J 轨迹偏移。
- J 每轮每客户端目标都记录 `changed_fraction_from_previous`；F 在固定边批次记录更新后的预测关系与所用目标之间的 MAE/MSE。
- 初检现在记录 public/test 特征探针及各客户端 `pretraining_record`；公共预测探针使用固定索引，而 `probe(..., indices=...)` 对预测计数、置信度和伪标签 CE/准确率统一使用同一子集。
- J 与历史 anchor 对齐时比较完整测试评估的 `clients` 和 `mean`；runner 入口检查 `__debug__`，优化模式启动会拒绝执行。

## Smoke 产物复核

只读检查最终产物 `experiments/stl10_diagnostics/results_smoke_final/completed.json`：记录为 3 个分支、各 3 轮，J 三轮与历史 B 匹配，J/F 首轮匹配；10 个列出的文件（含 `stages.csv`、`gradients.csv`、公共集中度 SVG）逐文件 SHA-256 均与清单一致。F 关系偏差字段、公共/测试特征探针和预训练记录均存在。没有重跑 smoke 或真实训练。主 AI 报告的 10 项单测通过及正式来源 sourcecheck 通过未在本次复核中重新执行。

