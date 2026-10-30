# 独立实现与审阅验收（2026-10-29）

## 报告模块子任务

- 调用模型：GPT-6 Luna，推理强度high。
- 分派任务：独立实现report.py，按case_id与seed分别计算D/B、D/E及内存汇总，不依赖旧实验包。
- 完成内容：逐方法CSV、逐配置配对JSON、内存CSV和Markdown报告；手造development case自测不同配置不混配。
- 结果与证据：`report.py`、开发测试中的配对数值核对，以及真实数据小规模CLI生成的报告。
- 主AI验证及验收：主AI修正了最大公共池C0措辞、预定seed数/partial判定和重复case/seed保护；13项测试及真实smoke结果检查通过，验收通过。

## 独立代码复审

- 调用模型：另一个GPT-6 Luna，推理强度high，未继承主AI详细推理，只给计划、路径和审查范围。
- 分派任务：只读核查固定私有数据/公共前缀、嵌套图、认证与学生训练时序、恢复/复用、成本和内存口径；独立运行开发测试。
- 完成内容：源码检查及 `D:\anaconda\python.exe -m unittest experiments.public_scaling.test_scaling -v`，13项全部通过。
- 结果与证据：config/data/graphs/head/engine/run/report.py；`test_nested_regular_graphs_and_prefix_matching`及`test_previous_public_update_is_in_next_certificate_delta`等测试。审阅者最初漏看图的标签重映射而误报前缀配对不嵌套，复算后主动撤回；其后重复报告的配对保护问题也已在主AI并行更新的版本解决，复测通过。最终未发现确认的阻断项。
- 主AI验证及验收：主AI独立验证真实Fashion-MNIST小规模all计划（15次方法训练、6次隔离内存回放）、完成后resume、case结果复用；清理旧代码后再次13项测试和新入口恢复通过。复审结论通过。

正式三种子、200轮扩展实验尚未运行，由用户执行；以上验证不作为正式省时或精度结论。没有启用research-rigor或其他skill。
