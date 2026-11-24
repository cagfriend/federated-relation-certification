# 当前待做实验

已完成的近期实验。

- **E54 STL-10 同场景基线比较与规模边界。** 三档规模覆盖全量 B、同界 E、当前 D 与 Demand，M4096 使用新种子确认。[正式报告](evidence/e54_paired_boundaries/report.md)
- **E55 Fashion-MNIST 跨数据确认。** 固定 M4096，在 IID 与强非 IID 下比较 B、同界 E 与 D，覆盖关系生成与完整头部耗时。[正式报告](evidence/e55_fashion_confirmation/report.md)
- **E56–E57 Fashion-MNIST 耗时归因与缓冲区复用确认。** E56 按阶段定位生成耗时，E57 在新种子上检验复用缓冲区的完整头部收益。[补充结果](evidence/FASHION_MNIST_GATHER_OPTIMIZATION_20261123.md)
- **E58–E59 STL-10 按需协议。** 在 M4096 对照显式请求、各端重建和仅聚合者重建，分别记录应用层字节及完整头部耗时。[结果与选择条件](evidence/DEMAND_SCHEDULE_PROTOCOLS_20261124.md)

[当前结果与复现](evidence/MATCHED_BASELINES_AND_FASHION_MNIST_20261123.md) · [此前计划与完成记录](history/NEXT_EXPERIMENTS_before_endpoint_bias.md) · [实验索引](evidence/EXPERIMENT_INDEX.md)
