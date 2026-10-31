> 主要统计已按用户确认的两次手动暂停剔除计时。IID seed404统一剔除r119，强非IID seed404统一剔除r100；各自全部配置/BED使用同一掩码。初始化/C0仍计，训练和质量指标保留全部200轮。原始计时未覆写，见上级PAUSE_EXCLUSION.json。暂停不计故障。

# 公共预算实验报告

所有性能对照先在同一 partition、case 和 seed 内配对，再对 seed 级结果取中位数。客户端是 seed 内观测，不视为独立 seed。三 seed 结果仅为探索性配对计时，不是独立新 seed 或隔离进程的性能确认；这里不与历史的其他机器运行时间比较。

## 配置与覆盖

| partition | case_id | seed | policy | steps | methods |
|:--|:--|--:|:--|--:|:--|
| dirichlet_0.1 | m16384_fixed8 | 404 | fixed | 8 | B, E, D |
| dirichlet_0.1 | m16384_full | 404 | full | 32 | B, E, D |
| dirichlet_0.1 | m4096_full | 404 | full | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8 | 505 | fixed | 8 | B, E, D |
| dirichlet_0.1 | m16384_full | 505 | full | 32 | B, E, D |
| dirichlet_0.1 | m4096_full | 505 | full | 8 | B, E, D |
| dirichlet_0.1 | m16384_fixed8 | 606 | fixed | 8 | B, E, D |
| dirichlet_0.1 | m16384_full | 606 | full | 32 | B, E, D |
| dirichlet_0.1 | m4096_full | 606 | full | 8 | B, E, D |
| iid | m16384_fixed8 | 404 | fixed | 8 | B, E, D |
| iid | m16384_full | 404 | full | 32 | B, E, D |
| iid | m4096_full | 404 | full | 8 | B, E, D |
| iid | m16384_fixed8 | 505 | fixed | 8 | B, E, D |
| iid | m16384_full | 505 | full | 32 | B, E, D |
| iid | m4096_full | 505 | full | 8 | B, E, D |
| iid | m16384_fixed8 | 606 | fixed | 8 | B, E, D |
| iid | m16384_full | 606 | full | 32 | B, E, D |
| iid | m4096_full | 606 | full | 8 | B, E, D |

## D 相对 B/E 的配对成本

比值小于 1 表示 D 较快；省时为参照方法秒数减 D 秒数。下表优先显示 generation、完整 head 与 C0+head；其他阶段耗时保留在 `paired_cost.csv` 和 `summary.json`。统计以 seed 为单位。

| partition | case_id | 对照 | 指标 | 配对 seeds | D 较快次数 | 中位比值 | 中位省秒 |
|:--|:--|:--|:--|--:|--:|--:|--:|
| dirichlet_0.1 | m16384_fixed8 | D_over_B | generation_seconds | 3 | 3 | 0.4237 | 17.7874 |
| dirichlet_0.1 | m16384_fixed8 | D_over_B | head_pipeline_seconds | 3 | 3 | 0.8488 | 19.1719 |
| dirichlet_0.1 | m16384_fixed8 | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.9040 | 19.1719 |
| dirichlet_0.1 | m16384_fixed8 | D_over_E | generation_seconds | 3 | 3 | 0.7809 | 3.7846 |
| dirichlet_0.1 | m16384_fixed8 | D_over_E | head_pipeline_seconds | 3 | 3 | 0.9681 | 3.2216 |
| dirichlet_0.1 | m16384_fixed8 | D_over_E | with_shared_preparation_seconds | 3 | 3 | 0.9787 | 3.2216 |
| dirichlet_0.1 | m16384_full | D_over_B | generation_seconds | 3 | 3 | 0.4236 | 18.0593 |
| dirichlet_0.1 | m16384_full | D_over_B | head_pipeline_seconds | 3 | 3 | 0.9115 | 18.0631 |
| dirichlet_0.1 | m16384_full | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.9348 | 18.0631 |
| dirichlet_0.1 | m16384_full | D_over_E | generation_seconds | 3 | 3 | 0.8102 | 3.1128 |
| dirichlet_0.1 | m16384_full | D_over_E | head_pipeline_seconds | 3 | 2 | 0.9878 | 2.2884 |
| dirichlet_0.1 | m16384_full | D_over_E | with_shared_preparation_seconds | 3 | 2 | 0.9912 | 2.2884 |
| dirichlet_0.1 | m4096_full | D_over_B | generation_seconds | 3 | 3 | 0.3863 | 4.6170 |
| dirichlet_0.1 | m4096_full | D_over_B | head_pipeline_seconds | 3 | 3 | 0.9582 | 5.3245 |
| dirichlet_0.1 | m4096_full | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.9734 | 5.3245 |
| dirichlet_0.1 | m4096_full | D_over_E | generation_seconds | 3 | 3 | 0.7615 | 1.0260 |
| dirichlet_0.1 | m4096_full | D_over_E | head_pipeline_seconds | 3 | 2 | 0.9936 | 0.7899 |
| dirichlet_0.1 | m4096_full | D_over_E | with_shared_preparation_seconds | 3 | 2 | 0.9960 | 0.7899 |
| iid | m16384_fixed8 | D_over_B | generation_seconds | 3 | 3 | 0.3306 | 26.6656 |
| iid | m16384_fixed8 | D_over_B | head_pipeline_seconds | 3 | 3 | 0.8656 | 21.8606 |
| iid | m16384_fixed8 | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.8994 | 21.8606 |
| iid | m16384_fixed8 | D_over_E | generation_seconds | 3 | 3 | 0.8044 | 2.9683 |
| iid | m16384_fixed8 | D_over_E | head_pipeline_seconds | 3 | 1 | 1.0132 | -1.8371 |
| iid | m16384_fixed8 | D_over_E | with_shared_preparation_seconds | 3 | 1 | 1.0095 | -1.8371 |
| iid | m16384_full | D_over_B | generation_seconds | 3 | 3 | 0.3346 | 24.8618 |
| iid | m16384_full | D_over_B | head_pipeline_seconds | 3 | 3 | 0.9179 | 18.5897 |
| iid | m16384_full | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.9398 | 18.5897 |
| iid | m16384_full | D_over_E | generation_seconds | 3 | 3 | 0.7961 | 2.9541 |
| iid | m16384_full | D_over_E | head_pipeline_seconds | 3 | 2 | 0.9833 | 3.4041 |
| iid | m16384_full | D_over_E | with_shared_preparation_seconds | 3 | 2 | 0.9869 | 3.4041 |
| iid | m4096_full | D_over_B | generation_seconds | 3 | 3 | 0.3179 | 5.2595 |
| iid | m4096_full | D_over_B | head_pipeline_seconds | 3 | 3 | 0.9752 | 2.3714 |
| iid | m4096_full | D_over_B | with_shared_preparation_seconds | 3 | 3 | 0.9842 | 2.3714 |
| iid | m4096_full | D_over_E | generation_seconds | 3 | 3 | 0.7660 | 0.7239 |
| iid | m4096_full | D_over_E | head_pipeline_seconds | 3 | 1 | 1.0330 | -2.8476 |
| iid | m4096_full | D_over_E | with_shared_preparation_seconds | 3 | 1 | 1.0186 | -2.8476 |

## 持久数组与通信量配对差

下表按同 case、同 seed 计算 D 减参照方法；负值表示 D 使用更少的持久数组字节或 traffic。

| partition | case_id | 对照 | paired seeds | 持久数组差中位数 bytes | traffic 差中位数 bytes |
|:--|:--|:--|--:|--:|--:|
| dirichlet_0.1 | m16384_fixed8 | D_over_B | 3 | 26577216 | 0 |
| dirichlet_0.1 | m16384_fixed8 | D_over_E | 3 | 0 | 0 |
| dirichlet_0.1 | m16384_full | D_over_B | 3 | 26577216 | 0 |
| dirichlet_0.1 | m16384_full | D_over_E | 3 | 0 | 0 |
| dirichlet_0.1 | m4096_full | D_over_B | 3 | 7113024 | 0 |
| dirichlet_0.1 | m4096_full | D_over_E | 3 | 0 | 0 |
| iid | m16384_fixed8 | D_over_B | 3 | 26577216 | 0 |
| iid | m16384_fixed8 | D_over_E | 3 | 0 | 0 |
| iid | m16384_full | D_over_B | 3 | 26577216 | 0 |
| iid | m16384_full | D_over_E | 3 | 0 | 0 |
| iid | m4096_full | D_over_B | 3 | 7113024 | 0 |
| iid | m4096_full | D_over_E | 3 | 0 | 0 |

## 固定预算带来的预算变化

下表比较同 partition/seed/M 下 fixed 与 full 的 B/E/D 阶段成本和学生步数；该变化来自减少学生预算，不能归因成 D 认证机制本身的贡献。

| partition | seed | M | method | steps full→fixed | head省秒 | C0+head省秒 | generation fraction 变化 | public steps 变化 |
|:--|--:|--:|:--|:--|--:|--:|--:|--:|
| dirichlet_0.1 | 404 | 16384 | B | 32→8 | 77.3152 | 77.4108 | 0.1046 | -28800 |
| dirichlet_0.1 | 404 | 16384 | E | 32→8 | 76.2399 | 76.3355 | 0.0755 | -28800 |
| dirichlet_0.1 | 404 | 16384 | D | 32→8 | 78.4240 | 78.5196 | 0.0608 | -28800 |
| dirichlet_0.1 | 505 | 16384 | B | 32→8 | 77.3045 | 77.3007 | 0.0965 | -28800 |
| dirichlet_0.1 | 505 | 16384 | E | 32→8 | 75.6907 | 75.6869 | 0.0701 | -28800 |
| dirichlet_0.1 | 505 | 16384 | D | 32→8 | 75.7510 | 75.7472 | 0.0541 | -28800 |
| dirichlet_0.1 | 606 | 16384 | B | 32→8 | 77.5345 | 77.5366 | 0.0874 | -28800 |
| dirichlet_0.1 | 606 | 16384 | E | 32→8 | 75.8218 | 75.8240 | 0.0541 | -28800 |
| dirichlet_0.1 | 606 | 16384 | D | 32→8 | 79.6200 | 79.6222 | 0.0457 | -28800 |
| iid | 404 | 16384 | B | 32→8 | 68.8590 | 68.8288 | 0.0983 | -28800 |
| iid | 404 | 16384 | E | 32→8 | 72.9458 | 72.9156 | 0.0504 | -28800 |
| iid | 404 | 16384 | D | 32→8 | 72.8948 | 72.8646 | 0.0414 | -28800 |
| iid | 505 | 16384 | B | 32→8 | 92.1758 | 92.1689 | 0.0935 | -28800 |
| iid | 505 | 16384 | E | 32→8 | 91.8234 | 91.8165 | 0.0465 | -28800 |
| iid | 505 | 16384 | D | 32→8 | 95.4468 | 95.4399 | 0.0380 | -28800 |
| iid | 606 | 16384 | B | 32→8 | 70.5439 | 70.5423 | 0.0955 | -28800 |
| iid | 606 | 16384 | E | 32→8 | 87.7797 | 87.7780 | 0.0609 | -28800 |
| iid | 606 | 16384 | D | 32→8 | 65.5766 | 65.5749 | 0.0368 | -28800 |

## ACC 质量护栏：固定预算对同 M full

使用 B 的最终指标作精确配对；ACC 下降不超过 0.01（1 个百分点）记为 within guardrail（含 1e-12 浮点容差）。NMI、ARI、最差客户端 ACC 和同客户端最小 ACC 变化作为描述性结果。缺少同 partition/seed/M 的 full 或必要指标时标为 pending。护栏是容忍范围，不是要求质量提升。

| partition | seed | M | fixed | full | ACC fixed−full | 护栏 | NMI 差 | ARI 差 | 最差ACC差 | 同客户端最小ACC差 | 状态 |
|:--|--:|--:|:--|:--|--:|:--|--:|--:|--:|--:|:--|
| dirichlet_0.1 | 404 | 16384 | m16384_fixed8 | m16384_full | -0.0050 | True | 0.0024 | -0.0032 | -0.0179 | -0.0179 | paired |
| dirichlet_0.1 | 505 | 16384 | m16384_fixed8 | m16384_full | -0.0015 | True | 0.0030 | -0.0004 | 0.0002 | -0.0118 | paired |
| dirichlet_0.1 | 606 | 16384 | m16384_fixed8 | m16384_full | -0.0027 | True | 0.0018 | -0.0014 | -0.0082 | -0.0082 | paired |
| iid | 404 | 16384 | m16384_fixed8 | m16384_full | -0.0003 | True | 0.0000 | -0.0000 | -0.0019 | -0.0019 | paired |
| iid | 505 | 16384 | m16384_fixed8 | m16384_full | -0.0003 | True | 0.0000 | -0.0001 | -0.0010 | -0.0011 | paired |
| iid | 606 | 16384 | m16384_fixed8 | m16384_full | 0.0001 | True | 0.0003 | 0.0002 | -0.0008 | -0.0008 | paired |

## 成本解释与边界

`head_pipeline_seconds` 是完整 head 流程耗时；`with_shared_preparation_seconds` 是包含共享准备的总口径。另列初始化、private、generation、exchange、public 阶段耗时。generation_fraction 与 teacher_recompute_fraction 用于解释证书生成占比和 teacher 刷新成本。新增持久数组内存及 traffic 按方法逐 case/seed 输出。隔离内存档案只在提供 profile 时报告。

这些数据用于评估主贡献的计算节省，允许小幅 ACC 回落；不将协作质量提升设为主要门槛，也不构成独立新 seed 的性能确认。

隔离内存 profiles：18。
