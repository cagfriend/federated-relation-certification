# 数值边界定位和试验性修补

判定：**通过**。25 个实例，55,044 个轮次—边位置。

| 实例 | 当前 D 对 B | 仅权重修补 | 仅稠密回退 | 合并残留 | 合并新增 | B 对有理数 |
|---|---:|---:|---:|---:|---:|---:|
| near_tie_k2 | 0 | 0 | 0 | 0 | 0 | 0 |
| cancellation_p53_d17_middle | 12 | 12 | 0 | 0 | 0 | 12 |
| prefix_p54_n32 | 0 | 0 | 0 | 0 | 0 | 0 |
| near_tie_k10 | 0 | 0 | 0 | 0 | 0 | 0 |
| near_tie_k64 | 0 | 0 | 0 | 0 | 0 | 0 |
| cancellation_p40_d17_middle | 0 | 0 | 0 | 0 | 0 | 0 |
| cancellation_p53_d17_after | 0 | 0 | 0 | 0 | 0 | 16 |
| cancellation_p53_d64_middle | 0 | 0 | 0 | 0 | 0 | 0 |
| cancellation_p60_d64_middle | 0 | 0 | 0 | 0 | 0 | 0 |
| cancellation_p60_d64_after | 0 | 0 | 0 | 0 | 0 | 74 |
| prefix_p40_n256 | 0 | 0 | 0 | 0 | 0 | 0 |
| prefix_p54_n256 | 0 | 0 | 0 | 0 | 0 | 0 |
| prefix_p60_n1024 | 0 | 0 | 0 | 0 | 0 | 0 |
| heldout_prefix_p55_n48 | 0 | 0 | 0 | 0 | 0 | 0 |
| heldout_prefix_p58_n192 | 0 | 0 | 0 | 0 | 0 | 0 |
| heldout_common_bias_p36 | 0 | 0 | 0 | 0 | 0 | 0 |
| heldout_common_bias_p48 | 0 | 0 | 0 | 0 | 0 | 0 |
| heldout_weight_prefix_p55_n48 | 408 | 0 | 408 | 0 | 0 | 0 |
| heldout_weight_prefix_p58_n192 | 1632 | 0 | 1632 | 0 | 0 | 0 |
| heldout_mixed_cancellation_p54_d17_middle | 15 | 15 | 0 | 0 | 0 | 30 |
| heldout_mixed_cancellation_p56_d33_after | 38 | 38 | 0 | 0 | 0 | 90 |
| heldout_weight_prefix_p56_n74 | 634 | 0 | 634 | 0 | 0 | 0 |
| heldout_mixed_cancellation_p55_d19_middle | 15 | 15 | 0 | 0 | 0 | 30 |
| heldout_mixed_cancellation_p57_d41_after | 38 | 38 | 0 | 0 | 0 | 90 |
| near_tie_k33 | 0 | 0 | 0 | 0 | 0 | 0 |

## 机制探针

| 实例 | 当前错边 | 端点排除 B 赢家 | 局部刷新与 B 不同 | 补候选即匹配 | B 切片刷新即匹配 | 精确前缀即匹配 |
|---|---:|---:|---:|---:|---:|---:|
| cancellation_p53_d17_middle | 12 | 9 | 3 | 3 | 3 | — |
| heldout_weight_prefix_p55_n48 | 408 | 408 | 0 | 408 | 0 | 408 |
| heldout_weight_prefix_p58_n192 | 1632 | 1632 | 0 | 1632 | 0 | 1632 |
| heldout_mixed_cancellation_p54_d17_middle | 15 | 10 | 5 | 0 | 5 | — |
| heldout_mixed_cancellation_p56_d33_after | 38 | 28 | 10 | 2 | 10 | — |

同一错边可涉及多个机制。探针复用原缓存，只干预当前轮；独立修补轨迹见 cases.csv。基准 B 是同环境的全批 float64；有理数对照用于识别 B 自身的舍入差异。

## 门槛检查

- e48_not_reproduced：通过
- weight_witness_remaining：通过
- cancellation_witness_remaining：通过
- combined_differs_from_b：通过
- replay_differs_from_b：通过

## 真实教师轨迹资源筛查

| 配置 | 已配对 | 合并生成耗时变化 | 全批触发（每次回放） | 合并额外持久缓存 B |
|---|---:|---:|---:|---:|
| 2022_iid_m4096 | 4 | +30.77% | 0 | +4,800 |
| 2022_dirichlet_0.1_m4096 | 4 | +29.37% | 0 | +4,800 |
| 2023_iid_m4096 | 4 | +27.32% | 0 | +4,800 |
| 2023_dirichlet_0.1_m4096 | 4 | +33.60% | 0 | +4,800 |

同进程配对回放，供筛查额外生成开销。完整训练时间与跨环境表现另需确认。
