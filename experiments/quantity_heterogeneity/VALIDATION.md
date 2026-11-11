# 开发验证与独立复审

2026-11-10。正式54主运行及可选6次内存回放尚未启动。旧代码、真实缓存、原结果不修改。

## 主AI验收证据

- 最终标准库unittest六项全部通过：容量和全覆盖/类别总量、确定性划分、非法容量拒绝；正式equal全部配置与P3 N6一致；equal划分与旧版本完全一致；准备缓存篡改/错误profile拒绝；旧引擎equal逐位轨迹对照；strong的B/E/D与内存回放及间隔评估/伪造容量账本拒绝。
- 只读核验正式P3全部18个同方法锚点、6份输入指针、P3 completed/finished封印及输入metadata摘要，无新准备或正式训练。
- AE/特征提取/KMeans客户端循环、公共样本抽样的AST与原准备器完全相同，旧P3冻结90份来源摘要不变。新环境冻结99份来源/协议及两份调度。
- 最终smoke位于`outputs/quantity_heterogeneity_review_20261110/smoke_final`：18主+6隔离内存，6个B/E/D组精确一致，关系20,736次、候选27,648次检查零错误。13份输出逐字节重生成；12个配对头部比值从原JSON复算一致；实际容量与各profile一致。
- 中断续跑fixture保留23条完整方法记录且字节不变，只重跑缺失的一条内存记录。完成目录resume只验证sealed manifest后返回，不新建日志或重复训练。进程起止时间与engine墙钟另行核验。
- KMeans可能报告合成小数据的重复点/少簇警告；smoke不作正式质量或性能证据。第一次开发smoke后补正了worker起止时间记录，最终验收仅使用最终源码下的smoke_final，均非正式训练。

[机器审计](../../outputs/quantity_heterogeneity_review_20261110/audit.json) · [审计脚本](../../outputs/quantity_heterogeneity_review_20261110/audit_smoke.py) · [核心复用核对](../../outputs/quantity_heterogeneity_review_20261110/check_reuse.py)。

## 子代理工作与主AI验收

|模型|分派任务|完成内容与证据|主AI复核/验收|
|---|---|---|---|
|GPT-6 Luna / high|data与partition实现|独立容量分配、准备身份/缓存校验、P3等量缓存只读复用|审阅并要求修正容量、IID路径、dtype和来源核验；AST、单元测试与完整smoke通过后验收|
|GPT-6 Luna / high|design、engine、runner实现|三档调度、旧训练核心复用、封印记录、equal锚点核验|主AI修正配置一致性、计量验证、父进程监测、完成resume和时间记录；18锚点预检及最终smoke通过后验收|
|GPT-6 Luna / high|独立测试实现|六项最终标准库测试，含错误输入/篡改和旧轨迹对照；代理报告通过|主AI在本机对最终六项重新执行，全部通过，验收|
|GPT-6 Luna / high|独立只读代码复审|审阅数据、源身份、锚点、容量账本和恢复，指出的阻塞项均修正；未运行正式训练|主AI核对修正并结合最终smoke、报表与续跑实测，验收通过|

## 解释边界

本实验等权聚合不变。跨档改变客户端容量、表示、伪标签、类别比例细节及私有SGD批次数，不把跨档差值归为认证收益。每配置每方法只有一次，不是独立重复性能确认。质量仅记严重退化边界，不要求ACC提高。正式计算收益及质量须等用户完成54次主运行后审核。
