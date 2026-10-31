> 主要统计已按用户确认的两次进程休眠剔除计时。强非IID seed606统一剔除r150，IID seed505统一剔除r143；各自全部档位/BED使用同一掩码。初始化/C0仍计，训练和质量指标保留全部200轮。原始计时未覆写，见上级PAUSE_EXCLUSION.json。休眠不计故障。

# 私有头部工作负载实验报告

所有性能对照先在同一 partition、case 和 seed 内配对，再对 seed 级结果取中位数。客户端是 seed 内观测，不视为独立 seed。三 seed 结果仅为探索性配对计时，不是独立新 seed 或隔离进程的性能确认；这里不与历史的其他机器运行时间比较。

## 配置与覆盖

| partition | case_id | seed | private_limit | public steps | methods |
|:--|:--|--:|:--|--:|:--|
| dirichlet_0.1 | m16384_fixed8_priv1024 | 404 | 1024 | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_priv2048 | 404 | 2048 | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_privfull | 404 | full | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_priv1024 | 505 | 1024 | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_priv2048 | 505 | 2048 | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_privfull | 505 | full | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_priv1024 | 606 | 1024 | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_priv2048 | 606 | 2048 | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8_privfull | 606 | full | 8 | B, E, D |
| iid | m16384_fixed8_priv1024 | 404 | 1024 | 8 | B, E, D |
| iid | m16384_fixed8_priv2048 | 404 | 2048 | 8 | B, E, D |
| iid | m16384_fixed8_privfull | 404 | full | 8 | B, E, D |
| iid | m16384_fixed8_priv1024 | 505 | 1024 | 8 | B, E, D |
| iid | m16384_fixed8_priv2048 | 505 | 2048 | 8 | B, E, D |
| iid | m16384_fixed8_privfull | 505 | full | 8 | B, E, D |
| iid | m16384_fixed8_priv1024 | 606 | 1024 | 8 | B, E, D |
| iid | m16384_fixed8_priv2048 | 606 | 2048 | 8 | B, E, D |
| iid | m16384_fixed8_privfull | 606 | full | 8 | B, E, D |

## D 相对 B/E 的配对成本

比值小于 1 表示 D 较快；省时为参照方法秒数减 D 秒数。下表优先显示 generation、完整 head 与 C0+head；其他阶段耗时保留在 `paired_cost.csv` 和 `summary.json`。统计以 seed 为单位。

| partition | case_id | 对照 | 指标 | 配对 seeds | D 较快次数 | 中位比值 | 中位省秒 |
|:--|:--|:--|:--|--:|--:|--:|--:|
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_B | generation_seconds | 3 | 3 | 0.3138 | 26.5304 |
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_B | head_pipeline_seconds | 3 | 3 | 0.6928 | 27.3107 |
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.8497 | 27.3107 |
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_E | generation_seconds | 3 | 0 | 1.1070 | -1.1882 |
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_E | head_pipeline_seconds | 3 | 0 | 1.0270 | -1.5781 |
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_E | with_shared_preparation_seconds | 3 | 0 | 1.0124 | -1.5781 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_B | generation_seconds | 3 | 3 | 0.4067 | 24.0600 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_B | head_pipeline_seconds | 3 | 3 | 0.7719 | 23.9226 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.8592 | 23.9226 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_E | generation_seconds | 3 | 3 | 0.8852 | 2.1193 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_E | head_pipeline_seconds | 3 | 3 | 0.9717 | 2.2609 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_E | with_shared_preparation_seconds | 3 | 3 | 0.9852 | 2.2609 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_B | generation_seconds | 3 | 3 | 0.4034 | 23.6043 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_B | head_pipeline_seconds | 3 | 3 | 0.8487 | 22.7648 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.9006 | 22.7648 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_E | generation_seconds | 3 | 3 | 0.7857 | 4.0784 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_E | head_pipeline_seconds | 3 | 3 | 0.9659 | 4.6676 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_E | with_shared_preparation_seconds | 3 | 3 | 0.9785 | 4.6676 |
| iid | m16384_fixed8_priv1024 | D_over_B | generation_seconds | 3 | 3 | 0.3571 | 24.0539 |
| iid | m16384_fixed8_priv1024 | D_over_B | head_pipeline_seconds | 3 | 3 | 0.7228 | 24.0672 |
| iid | m16384_fixed8_priv1024 | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.8369 | 24.0672 |
| iid | m16384_fixed8_priv1024 | D_over_E | generation_seconds | 3 | 0 | 1.0477 | -0.6217 |
| iid | m16384_fixed8_priv1024 | D_over_E | head_pipeline_seconds | 3 | 0 | 1.0126 | -0.7837 |
| iid | m16384_fixed8_priv1024 | D_over_E | with_shared_preparation_seconds | 3 | 0 | 1.0061 | -0.7837 |
| iid | m16384_fixed8_priv2048 | D_over_B | generation_seconds | 3 | 3 | 0.4128 | 19.0321 |
| iid | m16384_fixed8_priv2048 | D_over_B | head_pipeline_seconds | 3 | 3 | 0.7778 | 20.9777 |
| iid | m16384_fixed8_priv2048 | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.8600 | 20.9777 |
| iid | m16384_fixed8_priv2048 | D_over_E | generation_seconds | 3 | 3 | 0.8221 | 3.1414 |
| iid | m16384_fixed8_priv2048 | D_over_E | head_pipeline_seconds | 3 | 3 | 0.9569 | 3.1173 |
| iid | m16384_fixed8_priv2048 | D_over_E | with_shared_preparation_seconds | 3 | 3 | 0.9756 | 3.1173 |
| iid | m16384_fixed8_privfull | D_over_B | generation_seconds | 3 | 3 | 0.3305 | 25.7422 |
| iid | m16384_fixed8_privfull | D_over_B | head_pipeline_seconds | 3 | 3 | 0.8306 | 25.5856 |
| iid | m16384_fixed8_privfull | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.8817 | 25.5856 |
| iid | m16384_fixed8_privfull | D_over_E | generation_seconds | 3 | 3 | 0.8070 | 2.9551 |
| iid | m16384_fixed8_privfull | D_over_E | head_pipeline_seconds | 3 | 3 | 0.9785 | 2.8234 |
| iid | m16384_fixed8_privfull | D_over_E | with_shared_preparation_seconds | 3 | 3 | 0.9857 | 2.8234 |

## 持久数组与通信量配对差

下表按同 case、同 seed 计算 D 减参照方法；负值表示 D 使用更少的持久数组字节或 traffic。

| partition | case_id | 对照 | paired seeds | 持久数组差中位数 bytes | traffic 差中位数 bytes |
|:--|:--|:--|--:|--:|--:|
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_B | 3 | 26577216 | 0 |
| dirichlet_0.1 | m16384_fixed8_priv1024 | D_over_E | 3 | 0 | 0 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_B | 3 | 26577216 | 0 |
| dirichlet_0.1 | m16384_fixed8_priv2048 | D_over_E | 3 | 0 | 0 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_B | 3 | 26577216 | 0 |
| dirichlet_0.1 | m16384_fixed8_privfull | D_over_E | 3 | 0 | 0 |
| iid | m16384_fixed8_priv1024 | D_over_B | 3 | 26577216 | 0 |
| iid | m16384_fixed8_priv1024 | D_over_E | 3 | 0 | 0 |
| iid | m16384_fixed8_priv2048 | D_over_B | 3 | 26577216 | 0 |
| iid | m16384_fixed8_priv2048 | D_over_E | 3 | 0 | 0 |
| iid | m16384_fixed8_privfull | D_over_B | 3 | 26577216 | 0 |
| iid | m16384_fixed8_privfull | D_over_E | 3 | 0 | 0 |

## 减少私有工作负载带来的变化

下表比较同 partition/seed/M 下 reduced 与 full 私有工作负载的 B/E/D 阶段成本；该变化来自减少私有 SGD 预算，不能归因成 D 认证机制本身的贡献。认证收益只由同 case 内 D/B、D/E 配对衡量。

| partition | seed | method | private_limit | head省秒 | private省秒 | generation fraction 变化 | private steps 变化 |
|:--|--:|:--|--:|--:|--:|--:|--:|
| dirichlet_0.1 | 404 | B | 1024 | 92.7817 | 75.1122 | 0.1963 | -58800 |
| dirichlet_0.1 | 404 | E | 1024 | 96.2776 | 75.4123 | 0.0374 | -58800 |
| dirichlet_0.1 | 404 | D | 1024 | 90.8050 | 75.4688 | 0.0844 | -58800 |
| dirichlet_0.1 | 404 | B | 2048 | 60.4174 | 59.3107 | 0.1501 | -49200 |
| dirichlet_0.1 | 404 | E | 2048 | 64.0603 | 59.5689 | 0.0838 | -49200 |
| dirichlet_0.1 | 404 | D | 2048 | 61.6536 | 59.9741 | 0.0937 | -49200 |
| dirichlet_0.1 | 505 | B | 1024 | 62.6929 | 64.2736 | 0.1939 | -58800 |
| dirichlet_0.1 | 505 | E | 1024 | 73.5678 | 65.5045 | 0.0305 | -58800 |
| dirichlet_0.1 | 505 | D | 1024 | 67.2388 | 65.0091 | 0.0771 | -58800 |
| dirichlet_0.1 | 505 | B | 2048 | 50.5519 | 51.0025 | 0.1271 | -49200 |
| dirichlet_0.1 | 505 | E | 2048 | 53.5666 | 52.5207 | 0.0793 | -49200 |
| dirichlet_0.1 | 505 | D | 2048 | 50.0640 | 51.4306 | 0.0849 | -49200 |
| dirichlet_0.1 | 606 | B | 1024 | 29.6884 | 50.9859 | 0.1466 | -58800 |
| dirichlet_0.1 | 606 | E | 1024 | 43.5260 | 53.4897 | 0.0444 | -58800 |
| dirichlet_0.1 | 606 | D | 1024 | 37.4674 | 52.6863 | 0.0812 | -58800 |
| dirichlet_0.1 | 606 | B | 2048 | 13.4303 | 35.6309 | 0.1017 | -49200 |
| dirichlet_0.1 | 606 | E | 2048 | 17.8352 | 35.5922 | 0.0717 | -49200 |
| dirichlet_0.1 | 606 | D | 2048 | 16.9417 | 35.4424 | 0.0746 | -49200 |
| iid | 404 | B | 1024 | 57.0997 | 60.5637 | 0.1885 | -58800 |
| iid | 404 | E | 1024 | 63.1359 | 61.0348 | 0.0811 | -58800 |
| iid | 404 | D | 1024 | 58.2048 | 60.5690 | 0.1113 | -58800 |
| iid | 404 | B | 2048 | 54.6425 | 50.2199 | 0.1213 | -49200 |
| iid | 404 | E | 2048 | 51.3056 | 50.7604 | 0.1072 | -49200 |
| iid | 404 | D | 2048 | 51.2996 | 50.7102 | 0.0982 | -49200 |
| iid | 505 | B | 1024 | 58.9417 | 63.6430 | 0.1868 | -58800 |
| iid | 505 | E | 1024 | 63.2190 | 63.6564 | 0.0948 | -58800 |
| iid | 505 | D | 1024 | 60.5135 | 64.0778 | 0.1184 | -58800 |
| iid | 505 | B | 2048 | 43.5514 | 48.8472 | 0.1223 | -49200 |
| iid | 505 | E | 2048 | 43.1836 | 49.3833 | 0.0987 | -49200 |
| iid | 505 | D | 2048 | 41.5040 | 49.4470 | 0.0831 | -49200 |
| iid | 606 | B | 1024 | 67.6929 | 68.6305 | 0.1874 | -58800 |
| iid | 606 | E | 1024 | 69.1917 | 68.5796 | 0.0934 | -58800 |
| iid | 606 | D | 1024 | 65.5845 | 68.4376 | 0.1212 | -58800 |
| iid | 606 | B | 2048 | 71.4866 | 62.1235 | 0.1436 | -49200 |
| iid | 606 | E | 2048 | 65.6253 | 61.5410 | 0.1354 | -49200 |
| iid | 606 | D | 2048 | 66.2887 | 61.6253 | 0.1194 | -49200 |

## ACC 质量护栏：reduced 对同配置 full（逐方法）

使用各方法自身的最终指标作配对；ACC 下降不超过 0.01（1 个百分点）记为 within guardrail（含 1e-12 浮点容差）。NMI、ARI、最差客户端 ACC 和同客户端最小 ACC 变化作为描述性结果。缺少同 partition/seed/M 的 full 或必要指标时标为 pending。护栏是容忍范围，不是要求质量提升。

| partition | seed | method | private_limit | reduced | full | ACC reduced−full | 护栏 | NMI 差 | ARI 差 | 最差ACC差 | 同客户端最小ACC差 | 状态 |
|:--|--:|:--|--:|:--|:--|--:|:--|--:|--:|--:|--:|:--|
| dirichlet_0.1 | 404 | B | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2746 | False | -0.4421 | -0.2711 | -0.1786 | -0.3203 | paired |
| dirichlet_0.1 | 404 | E | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2746 | False | -0.4421 | -0.2711 | -0.1786 | -0.3203 | paired |
| dirichlet_0.1 | 404 | D | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2746 | False | -0.4421 | -0.2711 | -0.1786 | -0.3203 | paired |
| dirichlet_0.1 | 404 | B | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0306 | False | -0.0254 | -0.0426 | -0.0148 | -0.0731 | paired |
| dirichlet_0.1 | 404 | E | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0306 | False | -0.0254 | -0.0426 | -0.0148 | -0.0731 | paired |
| dirichlet_0.1 | 404 | D | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0306 | False | -0.0254 | -0.0426 | -0.0148 | -0.0731 | paired |
| dirichlet_0.1 | 505 | B | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2735 | False | -0.4526 | -0.2808 | -0.2298 | -0.3280 | paired |
| dirichlet_0.1 | 505 | E | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2735 | False | -0.4526 | -0.2808 | -0.2298 | -0.3280 | paired |
| dirichlet_0.1 | 505 | D | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2735 | False | -0.4526 | -0.2808 | -0.2298 | -0.3280 | paired |
| dirichlet_0.1 | 505 | B | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | 0.0076 | True | -0.0117 | 0.0000 | 0.0121 | -0.0394 | paired |
| dirichlet_0.1 | 505 | E | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | 0.0076 | True | -0.0117 | 0.0000 | 0.0121 | -0.0394 | paired |
| dirichlet_0.1 | 505 | D | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | 0.0076 | True | -0.0117 | 0.0000 | 0.0121 | -0.0394 | paired |
| dirichlet_0.1 | 606 | B | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2536 | False | -0.4033 | -0.2597 | -0.1267 | -0.3315 | paired |
| dirichlet_0.1 | 606 | E | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2536 | False | -0.4033 | -0.2597 | -0.1267 | -0.3315 | paired |
| dirichlet_0.1 | 606 | D | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.2536 | False | -0.4033 | -0.2597 | -0.1267 | -0.3315 | paired |
| dirichlet_0.1 | 606 | B | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0028 | True | -0.0047 | 0.0012 | 0.0584 | -0.0317 | paired |
| dirichlet_0.1 | 606 | E | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0028 | True | -0.0047 | 0.0012 | 0.0584 | -0.0317 | paired |
| dirichlet_0.1 | 606 | D | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0028 | True | -0.0047 | 0.0012 | 0.0584 | -0.0317 | paired |
| iid | 404 | B | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0211 | False | -0.0356 | -0.0280 | -0.0313 | -0.0313 | paired |
| iid | 404 | E | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0211 | False | -0.0356 | -0.0280 | -0.0313 | -0.0313 | paired |
| iid | 404 | D | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0211 | False | -0.0356 | -0.0280 | -0.0313 | -0.0313 | paired |
| iid | 404 | B | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0038 | True | -0.0064 | -0.0053 | -0.0069 | -0.0069 | paired |
| iid | 404 | E | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0038 | True | -0.0064 | -0.0053 | -0.0069 | -0.0069 | paired |
| iid | 404 | D | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0038 | True | -0.0064 | -0.0053 | -0.0069 | -0.0069 | paired |
| iid | 505 | B | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0209 | False | -0.0356 | -0.0289 | -0.0283 | -0.0325 | paired |
| iid | 505 | E | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0209 | False | -0.0356 | -0.0289 | -0.0283 | -0.0325 | paired |
| iid | 505 | D | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0209 | False | -0.0356 | -0.0289 | -0.0283 | -0.0325 | paired |
| iid | 505 | B | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0033 | True | -0.0051 | -0.0042 | -0.0074 | -0.0074 | paired |
| iid | 505 | E | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0033 | True | -0.0051 | -0.0042 | -0.0074 | -0.0074 | paired |
| iid | 505 | D | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0033 | True | -0.0051 | -0.0042 | -0.0074 | -0.0074 | paired |
| iid | 606 | B | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0240 | False | -0.0433 | -0.0354 | -0.0309 | -0.0309 | paired |
| iid | 606 | E | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0240 | False | -0.0433 | -0.0354 | -0.0309 | -0.0309 | paired |
| iid | 606 | D | 1024 | m16384_fixed8_priv1024 | m16384_fixed8_privfull | -0.0240 | False | -0.0433 | -0.0354 | -0.0309 | -0.0309 | paired |
| iid | 606 | B | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0045 | True | -0.0067 | -0.0054 | -0.0062 | -0.0067 | paired |
| iid | 606 | E | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0045 | True | -0.0067 | -0.0054 | -0.0062 | -0.0067 | paired |
| iid | 606 | D | 2048 | m16384_fixed8_priv2048 | m16384_fixed8_privfull | -0.0045 | True | -0.0067 | -0.0054 | -0.0062 | -0.0067 | paired |

## 成本解释与边界

`head_pipeline_seconds` 是完整 head 流程耗时；`with_shared_preparation_seconds` 是包含共享准备的总口径。另列初始化、private、generation、exchange、public 阶段耗时。generation_fraction 与 teacher_recompute_fraction 用于解释证书生成占比和 teacher 刷新成本。新增持久数组内存及 traffic 按方法逐 case/seed 输出。隔离内存档案只在提供 profile 时报告。

私有上限只减少每轮头部 SGD 处理的样本量；编码器仍由完整私有集预训练并冻结，准备成本 C0 按完整口径计入，不能把本实验称为小私有数据集实验。这些数据用于评估主贡献的计算节省，允许小幅 ACC 回落；不将协作质量提升设为主要门槛，也不构成独立新 seed 的性能确认。

隔离内存 profiles：18。
