# 偏置净变化数值对照

范围为完整矩阵，判定为**未通过**。共 21 个实例。
共同核对 52,509 个边位置（每个位置比较新旧 D）。

| 实例 | B 对有理数错边 | 旧 D 对 B | 新 D 对 B | 已修复 | 残留 | 新引入 | 配对轮次 |
|---|---:|---:|---:|---:|---:|---:|---:|
| near_tie_k2 | 0 | 0 | 0 | 0 | 0 | 0 | 11/11 |
| cancellation_p53_d17_middle | 12 | 13 | 12 | 4 | 9 | 3 | 11/11 |
| prefix_p54_n32 | 0 | 272 | 0 | 272 | 0 | 0 | 38/38 |
| near_tie_k10 | 0 | 0 | 0 | 0 | 0 | 0 | 11/11 |
| near_tie_k64 | 0 | 0 | 0 | 0 | 0 | 0 | 11/11 |
| cancellation_p40_d17_middle | 0 | 0 | 0 | 0 | 0 | 0 | 11/11 |
| cancellation_p53_d17_after | 16 | 10 | 0 | 10 | 0 | 0 | 11/11 |
| cancellation_p53_d64_middle | 0 | 0 | 0 | 0 | 0 | 0 | 11/11 |
| cancellation_p60_d64_middle | 0 | 0 | 0 | 0 | 0 | 0 | 11/11 |
| cancellation_p60_d64_after | 74 | 0 | 0 | 0 | 0 | 0 | 11/11 |
| prefix_p40_n256 | 0 | 0 | 0 | 0 | 0 | 0 | 262/262 |
| prefix_p54_n256 | 0 | 2176 | 0 | 2176 | 0 | 0 | 262/262 |
| prefix_p60_n1024 | 0 | 8704 | 0 | 8704 | 0 | 0 | 1030/1030 |
| heldout_prefix_p55_n48 | 0 | 408 | 0 | 408 | 0 | 0 | 54/54 |
| heldout_prefix_p58_n192 | 0 | 1632 | 0 | 1632 | 0 | 0 | 198/198 |
| heldout_common_bias_p36 | 0 | 0 | 0 | 0 | 0 | 0 | 9/9 |
| heldout_common_bias_p48 | 0 | 0 | 0 | 0 | 0 | 0 | 9/9 |
| heldout_weight_prefix_p55_n48 | 0 | 408 | 408 | 0 | 408 | 0 | 54/54 |
| heldout_weight_prefix_p58_n192 | 0 | 1632 | 1632 | 0 | 1632 | 0 | 198/198 |
| heldout_mixed_cancellation_p54_d17_middle | 30 | 66 | 15 | 63 | 3 | 12 | 15/15 |
| heldout_mixed_cancellation_p56_d33_after | 90 | 33 | 38 | 24 | 9 | 29 | 15/15 |

## 判定细目

- `incomplete`：无
- `baseline_witness_not_reproduced`：无
- `bias_prefix_still_differs`：无
- `new_differences`：cancellation_p53_d17_middle, heldout_mixed_cancellation_p54_d17_middle, heldout_mixed_cancellation_p56_d33_after

同一轮、同一边编号用于判定已修复、残留与新引入。方法异常后的轮次缺失计数，完整性未通过。权重前缀及大数相消的残留单列。
CSV 含候选排除、回退标签分歧和打分端点数。JSON 与 NPZ 保留第一处异常的可复现证据。
