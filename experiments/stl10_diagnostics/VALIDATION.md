# 运行前验证

2026-11-01。尚未运行正式40轮诊断，不对真实退化原因下结论。

- `D:\anaconda\python.exe -m unittest experiments.stl10_diagnostics.test_probes experiments.stl10_diagnostics.test_run`：10/10通过。覆盖固定子集统计、探针不改参数/输入/全局随机状态、最近中心小实例、J与原训练实现对齐、诊断开关不改轨迹、F首轮等价/后续固定目标、P与纯私有更新等价、锚点篡改检测。
- 最终smoke目录：`results_smoke_final`，使用已有显式合成夹具，P/J/F各3轮。J匹配旧B的3轮非计时轨迹与对应评估；J/F第1轮参数与实际目标一致；10个产物哈希均核验，包括逐客户端CSV、SVG、固定目标和各臂JSON。
- 旧STL-10正式实验`check_environment`通过，确认原源码与冻结配置未改。正式模式只读取原缓存，不触发AE、KMeans重训或数据下载。
- smoke不构成真实数据诊断证据。额外检查改变诊断运行时长，本包输出不作为B/E/D性能测量。

## 子代理与验收

|模型|任务|完成内容与证据|主AI核验与结论|
|---|---|---|---|
|GPT-6 Luna / high|实现只读特征、中心、头部与梯度探针及测试；跟进子集统计问题|`probes.py`、`test_probes.py`，7项探针测试。按主AI反馈修复indices此前只影响部分统计的问题，新增子集等价测试|主AI阅读实现，运行全部10项单测及最终smoke，验收修正版本|
|GPT-6 Luna / high|独立只读审阅runner的方案符合性；复审修正与最终产物|提出目标变化比例、F拟合偏差、public/test特征检查、评估核验及-O绕过问题；最终报告确认均补齐，独立检查10个smoke产物哈希，没有新阻塞项|主AI补齐缺项并核对报告证据，通过旧源码检查和最终流程；验收。独立代理没有自行重跑正式训练，单测执行证据来自主AI|

独立报告：`outputs/stl10_diagnostics_setup_20261101/INDEPENDENT_REVIEW.md`。不允许以Python `-O`运行，以免关闭验收断言。没有上传GitHub，也没有启动正式实验。
