# 特征收集方式筛选

筛选状态 **screen_passed**。进入下一阶段的候选为 **take_reuse**。

| 配置 | 候选 | 有效配对块 | 收集加打分省时 | 达到 10% |
| --- | --- | ---: | ---: | --- |
| 3101_dirichlet_0.1 | take_allocate | 6 | +2.23% | 否 |
| 3101_dirichlet_0.1 | take_reuse | 6 | +34.70% | 是 |
| 3102_dirichlet_0.1 | take_allocate | 6 | +1.38% | 否 |
| 3102_dirichlet_0.1 | take_reuse | 6 | +30.51% | 是 |
| 3103_dirichlet_0.1 | take_allocate | 6 | +1.62% | 否 |
| 3103_dirichlet_0.1 | take_reuse | 6 | +33.57% | 是 |

收集加打分包含偏置加法和赢家选择。复用缓冲区首次分配计入耗时。另保留各特征宽度和刷新比例下的收集耗时与总耗时。
