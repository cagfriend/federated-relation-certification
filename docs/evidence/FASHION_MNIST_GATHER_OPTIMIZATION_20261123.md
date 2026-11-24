# E56–E57 · Fashion-MNIST 的关系生成归因与缓冲区复用确认

两项补充实验沿用 E55 的 Fashion-MNIST M4096、K10、六个异宽客户端、每端 200 个私有样本、200 轮和两步公共更新。全量路径 B 对每个公共样本打分一次。原版 D 和缓冲区复用 D 使用同一偏置净变化认证界。改动位于重算端点的特征收集环节。[E55 证据与设置](MATCHED_BASELINES_AND_FASHION_MNIST_20261123.md)

## E56 · 生成阶段归因

种子 3101、3102、3103 分别覆盖 IID 和 Dirichlet α=0.1。24 个无插桩 B/D 配对块和 6 个独立插桩配对块全部有效。三个强非 IID 配置中，原版 D 的无插桩生成耗时平均比 B 多 0.127–0.407 秒，各组的四个配对均更慢。插桩测得 D 的打分耗时少 0.706–0.780 秒，收集重算端点所需特征的行拷贝增加 0.355–0.515 秒，是三个配置中最大的新增单项开销。三个强非 IID 配置均通过预设归因判据。IID 的三个配置中有两个出现插桩和无插桩耗时差方向相反，阶段归因保留为待复核。[报告](e56_fashion_generation_profile/report.md) · [阶段差](e56_fashion_generation_profile/diagnostics.csv) · [计时配对](e56_fashion_generation_profile/paired_blocks.csv)

## E57 · 筛选与新种子确认

在 E56 三个强非 IID 配置的真实刷新请求上，使用 `np.take` 每次分配输出的版本节省 1.38%–2.23% 的收集加打分耗时，三组均未达到 10% 门槛。复用同一块连续输出缓冲区的版本节省 30.51%–34.70%，三个种子均达标。冻结后在 3111、3112、3113 三个新种子及两种划分上与 B、原版 D 对照。36 个无插桩配对块、108 次计时均有效。[筛选报告](e57_fashion_gather_optimization/screening/report.md) · [宽度与重算比例分层](e57_fashion_gather_optimization/screening/strata.csv)

下表为复用版 D 的完整头部平均省时，正值表示更快。每格六个配对。

| 划分 | 种子 | 相对原版 D | 相对全量 B |
| --- | ---: | ---: | ---: |
| IID | 3111 | +6.52% | +4.91% |
| IID | 3112 | +3.99% | +7.13% |
| IID | 3113 | +7.11% | +8.21% |
| Dirichlet α=0.1 | 3111 | −1.02% | −1.28% |
| Dirichlet α=0.1 | 3112 | +8.46% | −0.65% |
| Dirichlet α=0.1 | 3113 | +8.76% | +0.07% |

相对原版 D，强非 IID 有 2/3 个种子达到平均省时 ≥3% 且至少赢 5/6 块，IID 三个种子均提速，达到主验收条件。强非 IID 的 3111 平均生成省 0.108 秒且完整头部赢 4/6 块。另两个配对同时出现较慢的私有更新、交换及公共更新，保留在均值内。相对全量 B，IID 有 3/3 个种子达到同一省时与胜场门槛。强非 IID 有 0/3 个种子达标，平均耗时与 B 接近。[确认报告](e57_fashion_gather_optimization/confirmation/report.md) · [逐格结果](e57_fashion_gather_optimization/confirmation/seeds.csv) · [逐块计时](e57_fashion_gather_optimization/confirmation/paired_blocks.csv)

18 次独立审计共核对 44,236,800 个边位置，三种方法的关系、聚合计数、学生目标、头参数和应用层字节逐轮一致。两个 D 的刷新索引和认证缓存一致。当前单线程串行运行每进程额外持有一块 8 MiB 逻辑容量的缓冲区，首次分配计入生成及完整头部计时。E56 的阶段时间用于归因，E57 的性能结论采用无插桩计时。[资源明细](e57_fashion_gather_optimization/confirmation/runs.csv)

## 可复现范围

E55 的 B/E/D 对照对应原版 D。E57 报告的是缓冲区复用实现及其新种子对照。两项补充实验支持在固定表示和受测配置下保持全量关系与训练轨迹，以及完整头部收益随工作负载变化的结论。

在仓库根目录准备 Fashion-MNIST 的四份官方 IDX gzip，启动相应入口。正式运行使用单线程 CPU、插电并读取休眠状态。第二个入口可通过 `--development-cache` 复用 E56 的缓存。输入目录、短测和续跑见各包说明。[E56 入口](../../snapshot_routing/fashion_generation_profile/README.md) · [E57 入口](../../snapshot_routing/fashion_gather_optimization/README.md)

## 原始记录

`tar -xf archives/<归档名>.tar.xz` 在仓库根目录恢复原路径。档案保留逐运行记录、配对、评估、派生表与回执的原始字节，逐文件和压缩包 SHA-256 见清单。公开来源清单保留原执行清单的 SHA-256、源码与输入指纹，省略机器名及本机缓存绝对路径。复跑通过原始数据重建准备资产。

- [E56 原始记录](../../archives/e56_fashion_generation_profile_raw_records_20261123.tar.xz) · [SHA-256 清单](../../archives/e56_fashion_generation_profile_raw_records_20261123.manifest.json) · [来源](e56_fashion_generation_profile/provenance.json)
- [E57 原始记录](../../archives/e57_fashion_gather_optimization_raw_records_20261123.tar.xz) · [SHA-256 清单](../../archives/e57_fashion_gather_optimization_raw_records_20261123.manifest.json) · [筛选来源](e57_fashion_gather_optimization/screening/provenance.json) · [确认来源](e57_fashion_gather_optimization/confirmation/provenance.json)
