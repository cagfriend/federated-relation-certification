# 关系认证浮点边界核验

完成 13 个固定合成实例，其中 5 个未满足完整 E/D 对 B 零关系差异。E/D 对 B 共核对 79,386 条边。

| 实例 | 轮次 | B 对有理数边差异 | E 对 B 边差异 | D 对 B 边差异 | 生成异常 |
|---|---:|---:|---:|---:|---:|
| near_tie_k2 | 11 | 0 | 0 | 0 | 0 |
| cancellation_p53_d17_middle | 11 | 12 | 13 | 13 | 0 |
| prefix_p54_n32 | 38 | 0 | 272 | 272 | 0 |
| near_tie_k10 | 11 | 0 | 0 | 0 | 0 |
| near_tie_k64 | 11 | 0 | 0 | 0 | 0 |
| cancellation_p40_d17_middle | 11 | 0 | 0 | 0 | 0 |
| cancellation_p53_d17_after | 11 | 16 | 10 | 10 | 0 |
| cancellation_p53_d64_middle | 11 | 0 | 0 | 0 | 0 |
| cancellation_p60_d64_middle | 11 | 0 | 0 | 0 | 0 |
| cancellation_p60_d64_after | 11 | 74 | 0 | 0 | 0 |
| prefix_p40_n256 | 262 | 0 | 0 | 0 | 0 |
| prefix_p54_n256 | 262 | 0 | 2176 | 2176 | 0 |
| prefix_p60_n1024 | 1030 | 0 | 8704 | 8704 | 0 |

B 为原全量 float64 实现。有理数参考对传入的 binary64 特征和权重做精确乘加。两类差异按独立参照统计。

cases.csv 另列候选排除与回退标签分歧的次数。各例 JSON 记录每类首见差异和中间状态。witnesses 目录保存出现任一差异的完整原始输入序列。
