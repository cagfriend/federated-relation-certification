# 实验与证据总索引

本次按远端基线 `46b25e333228` 逐目录整理。原报告、原始记录、预注册、审阅及源码不移动、不改写。

B=全量教师关系生成，E=逐样本认证，D=关系认证；三者使用相同自适应编码。历史A/C仅用于拆开计算与通信。技术重复、不同种子与边检查次数分别记录。

|编号|实验|要验证的问题|结论入口|
|---|---|---|---|
|E01|[合成开销、更新幅度扫描与留出复核](#e01)|验证认证与自适应编码各自的收益，定位小更新有利区间。|[原实验说明](../../experiments/overhead_benchmark/README.md)|

<a id="e01"></a>
## E01 合成开销、更新幅度扫描与留出复核

|项目|记录|
|---|---|
|实验目录|`experiments/overhead_benchmark/`|
|配置与对照|固定特征、图和参数轨迹；初始A/B/C/D拆分计算与编码，随后B/E/D扫描；探索101/202/303，留出404/505/606/707/808。|
|验证问题|验证认证与自适应编码各自的收益，定位小更新有利区间。|
|主要结果|留出0.05/0.10/0.12在五种子同时胜B/E；0.16接近边界，不支持固定转折阈值。|
|结论边界与异常|合成扰动scale不是学习率；不涉及真实训练质量；旧驱动已清理。|
|代码状态|本提交有0个Python文件。已清理原驱动，只保留证据；旧命令不可直接运行。|

**原始说明及协议：** [experiments/overhead_benchmark/README.md](../../experiments/overhead_benchmark/README.md) · [experiments/overhead_benchmark/HOLDOUT_INDEPENDENT_REVIEW.md](../../experiments/overhead_benchmark/HOLDOUT_INDEPENDENT_REVIEW.md) · [experiments/overhead_benchmark/INDEPENDENT_REVIEW.md](../../experiments/overhead_benchmark/INDEPENDENT_REVIEW.md) · [experiments/overhead_benchmark/SWEEP_INDEPENDENT_REVIEW.md](../../experiments/overhead_benchmark/SWEEP_INDEPENDENT_REVIEW.md) · [experiments/overhead_benchmark/VALIDATION.md](../../experiments/overhead_benchmark/VALIDATION.md)

**结果与审核：** [experiments/overhead_benchmark/HOLDOUT_RESULTS_20261029.md](../../experiments/overhead_benchmark/HOLDOUT_RESULTS_20261029.md) · [experiments/overhead_benchmark/RESULTS_ONLY.md](../../experiments/overhead_benchmark/RESULTS_ONLY.md) · [experiments/overhead_benchmark/SWEEP_RESULTS_20261028.md](../../experiments/overhead_benchmark/SWEEP_RESULTS_20261028.md)

**归档、清单与原始文件：** [archives/overhead_benchmark_raw_records_01.zip](../../archives/overhead_benchmark_raw_records_01.zip) · [archives/overhead_benchmark_raw_records_02.zip](../../archives/overhead_benchmark_raw_records_02.zip) · [archives/overhead_benchmark_raw_records_03.zip](../../archives/overhead_benchmark_raw_records_03.zip) · [archives/overhead_benchmark_raw_records_04.zip](../../archives/overhead_benchmark_raw_records_04.zip) · [archives/overhead_benchmark_raw_records_05.zip](../../archives/overhead_benchmark_raw_records_05.zip) · [archives/overhead_benchmark_raw_records_06.zip](../../archives/overhead_benchmark_raw_records_06.zip) · [archives/overhead_benchmark_raw_records_07.zip](../../archives/overhead_benchmark_raw_records_07.zip) · [archives/overhead_benchmark_raw_records_08.zip](../../archives/overhead_benchmark_raw_records_08.zip) · [archives/overhead_benchmark_raw_records_09.zip](../../archives/overhead_benchmark_raw_records_09.zip) · [archives/overhead_benchmark_raw_records_10.zip](../../archives/overhead_benchmark_raw_records_10.zip)
|E02|[首轮真实IID训练](#e02)|自然SGD下的关系一致性、头部净收益和空间代价。|[原实验说明](../../experiments/real_iid/README.md)|

<a id="e02"></a>
## E02 首轮真实IID训练

|项目|记录|
|---|---|
|实验目录|`experiments/real_iid/`|
|配置与对照|Fashion-MNIST，6异宽MLP客户端、M4096/K10/200轮；101/202/303；Local/B/E/D。|
|验证问题|自然SGD下的关系一致性、头部净收益和空间代价。|
|主要结果|D/B生成省68.88%、完整头省4.49%；D/E完整头省1.27%，仅2/3更快。|
|结论边界与异常|B相对Local没有明确稳定质量提升；旧驱动已清理。|
|代码状态|本提交有0个Python文件。已清理原驱动，只保留证据；旧命令不可直接运行。|

**原始说明及协议：** [experiments/real_iid/README.md](../../experiments/real_iid/README.md) · [experiments/real_iid/EXPERIMENT_PLAN.md](../../experiments/real_iid/EXPERIMENT_PLAN.md) · [experiments/real_iid/INDEPENDENT_REVIEW.md](../../experiments/real_iid/INDEPENDENT_REVIEW.md) · [experiments/real_iid/VALIDATION.md](../../experiments/real_iid/VALIDATION.md) · [experiments/real_iid/analysis_20261029/INDEPENDENT_REVIEW.md](../../experiments/real_iid/analysis_20261029/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/real_iid/RESULTS_ONLY.md](../../experiments/real_iid/RESULTS_ONLY.md) · [experiments/real_iid/analysis_20261029/RESULTS_REVIEW.md](../../experiments/real_iid/analysis_20261029/RESULTS_REVIEW.md) · [experiments/real_iid/results_full/report.md](../../experiments/real_iid/results_full/report.md) · [experiments/real_iid/results_smoke/report.md](../../experiments/real_iid/results_smoke/report.md)

**归档、清单与原始文件：** [archives/real_iid_raw_records_01.zip](../../archives/real_iid_raw_records_01.zip) · [experiments/real_iid/SOURCE_MANIFEST.json](../../experiments/real_iid/SOURCE_MANIFEST.json) · [experiments/real_iid/analysis_20261029/MANIFEST.json](../../experiments/real_iid/analysis_20261029/MANIFEST.json) · [experiments/real_iid/results_full/completed.json](../../experiments/real_iid/results_full/completed.json) · [experiments/real_iid/results_smoke/completed.json](../../experiments/real_iid/results_smoke/completed.json)
|E03|[公共样本规模](#e03)|公共规模增大时，生成收益能否转成完整头部收益。|[原实验说明](../../experiments/public_scaling/README.md)|

<a id="e03"></a>
## E03 公共样本规模

|项目|记录|
|---|---|
|实验目录|`experiments/public_scaling/`|
|配置与对照|Fashion-MNIST，M4096/8192/16384、degree1、6客户端、K10、200轮；404/505/606，27次方法运行。|
|验证问题|公共规模增大时，生成收益能否转成完整头部收益。|
|主要结果|D/B完整头省5.81%/9.50%/11.39%；D/E仅约0.93%–1.36%；同配置轨迹、通信一致。|
|结论边界与异常|同时改变边数与公共学生更新步数；不能单独归因于公共信息量。|
|代码状态|本提交有13个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/public_scaling/README.md](../../experiments/public_scaling/README.md) · [experiments/public_scaling/INDEPENDENT_REVIEW.md](../../experiments/public_scaling/INDEPENDENT_REVIEW.md) · [experiments/public_scaling/VALIDATION.md](../../experiments/public_scaling/VALIDATION.md)

**结果与审核：** [experiments/public_scaling/results_public/report.md](../../experiments/public_scaling/results_public/report.md) · [experiments/public_scaling/validation_reuse_20261029/report.md](../../experiments/public_scaling/validation_reuse_20261029/report.md) · [experiments/public_scaling/validation_smoke_20261029/report.md](../../experiments/public_scaling/validation_smoke_20261029/report.md) · [outputs/public_scaling_results_20261030/INDEPENDENT_REVIEW.md](../../outputs/public_scaling_results_20261030/INDEPENDENT_REVIEW.md) · [outputs/public_scaling_results_20261030/RESULTS_REVIEW.md](../../outputs/public_scaling_results_20261030/RESULTS_REVIEW.md)

**归档、清单与原始文件：** [archives/public_scaling_raw_records_01.zip](../../archives/public_scaling_raw_records_01.zip) · [archives/public_scaling_raw_records_02.zip](../../archives/public_scaling_raw_records_02.zip) · [experiments/public_scaling/SOURCE_MANIFEST.json](../../experiments/public_scaling/SOURCE_MANIFEST.json) · [experiments/public_scaling/results_public/completed.json](../../experiments/public_scaling/results_public/completed.json) · [experiments/public_scaling/validation_reuse_20261029/completed.json](../../experiments/public_scaling/validation_reuse_20261029/completed.json) · [experiments/public_scaling/validation_smoke_20261029/completed.json](../../experiments/public_scaling/validation_smoke_20261029/completed.json)
|E04|[固定公共库的图密度](#e04)|更密图是否扩大关系认证收益。|[原实验说明](../../experiments/graph_density/README.md)|

<a id="e04"></a>
## E04 固定公共库的图密度

|项目|记录|
|---|---|
|实验目录|`experiments/graph_density/`|
|配置与对照|M4096、degree1/4/8、三个既有seed；degree1复用先前结果，新增18次方法运行。|
|验证问题|更密图是否扩大关系认证收益。|
|主要结果|D/E完整头省1.29%/−0.28%/−0.17%；密图优势消失。|
|结论边界与异常|增加degree也增加公共学生预算；负数表示D更慢。|
|代码状态|本提交有4个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/graph_density/README.md](../../experiments/graph_density/README.md) · [experiments/graph_density/INDEPENDENT_REVIEW.md](../../experiments/graph_density/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/graph_density/results_graph/graph_analysis/report.md](../../experiments/graph_density/results_graph/graph_analysis/report.md) · [experiments/graph_density/results_graph/report.md](../../experiments/graph_density/results_graph/report.md) · [outputs/graph_density_results_20261030/INDEPENDENT_REVIEW.md](../../outputs/graph_density_results_20261030/INDEPENDENT_REVIEW.md) · [outputs/graph_density_results_20261030/RESULTS_REVIEW.md](../../outputs/graph_density_results_20261030/RESULTS_REVIEW.md)

**归档、清单与原始文件：** [archives/graph_density_raw_records_404.zip](../../archives/graph_density_raw_records_404.zip) · [archives/graph_density_raw_records_505.zip](../../archives/graph_density_raw_records_505.zip) · [archives/graph_density_raw_records_606.zip](../../archives/graph_density_raw_records_606.zip) · [experiments/graph_density/results_graph/completed.json](../../experiments/graph_density/results_graph/completed.json)
|E05|[E/D成本分解](#e05)|省掉的教师计算是否被认证维护抵消。|[原实验说明](../../experiments/cost_diagnostics/README.md)|

<a id="e05"></a>
## E05 E/D成本分解

|项目|记录|
|---|---|
|实验目录|`experiments/cost_diagnostics/`|
|配置与对照|9组真实E轨迹；普通/插桩E/D缓存消费相同教师快照，排除首次初始化。|
|验证问题|省掉的教师计算是否被认证维护抵消。|
|主要结果|degree1有净节省，degree4接近持平，degree8额外非教师成本超过教师节省。|
|结论边界与异常|插桩回放是机制诊断，不能替代完整训练测速。|
|代码状态|本提交有4个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/cost_diagnostics/README.md](../../experiments/cost_diagnostics/README.md) · [experiments/cost_diagnostics/INDEPENDENT_REVIEW.md](../../experiments/cost_diagnostics/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/cost_diagnostics/results_full/report.md](../../experiments/cost_diagnostics/results_full/report.md) · [outputs/cost_diagnostics_results_20261030/INDEPENDENT_REVIEW.md](../../outputs/cost_diagnostics_results_20261030/INDEPENDENT_REVIEW.md) · [outputs/cost_diagnostics_results_20261030/RESULTS_REVIEW.md](../../outputs/cost_diagnostics_results_20261030/RESULTS_REVIEW.md)

**归档、清单与原始文件：** [archives/cost_diagnostics_raw_records_m4096_d1_seed_404.zip](../../archives/cost_diagnostics_raw_records_m4096_d1_seed_404.zip) · [archives/cost_diagnostics_raw_records_m4096_d1_seed_505.zip](../../archives/cost_diagnostics_raw_records_m4096_d1_seed_505.zip) · [archives/cost_diagnostics_raw_records_m4096_d1_seed_606.zip](../../archives/cost_diagnostics_raw_records_m4096_d1_seed_606.zip) · [archives/cost_diagnostics_raw_records_m4096_d4_seed_404.zip](../../archives/cost_diagnostics_raw_records_m4096_d4_seed_404.zip) · [archives/cost_diagnostics_raw_records_m4096_d4_seed_505.zip](../../archives/cost_diagnostics_raw_records_m4096_d4_seed_505.zip) · [archives/cost_diagnostics_raw_records_m4096_d4_seed_606.zip](../../archives/cost_diagnostics_raw_records_m4096_d4_seed_606.zip) · [archives/cost_diagnostics_raw_records_m4096_d8_seed_404.zip](../../archives/cost_diagnostics_raw_records_m4096_d8_seed_404.zip) · [archives/cost_diagnostics_raw_records_m4096_d8_seed_505.zip](../../archives/cost_diagnostics_raw_records_m4096_d8_seed_505.zip) · [archives/cost_diagnostics_raw_records_m4096_d8_seed_606.zip](../../archives/cost_diagnostics_raw_records_m4096_d8_seed_606.zip) · [experiments/cost_diagnostics/SOURCE_MANIFEST.json](../../experiments/cost_diagnostics/SOURCE_MANIFEST.json) · [experiments/cost_diagnostics/results_full/completed.json](../../experiments/cost_diagnostics/results_full/completed.json)
|E06|[连续缓存路径选择](#e06)|动态规则能否优于静态E/D选择。|[原实验说明](../../experiments/path_selection/README.md)|

<a id="e06"></a>
## E06 连续缓存路径选择

|项目|记录|
|---|---|
|实验目录|`experiments/path_selection/`|
|配置与对照|degree1/4/8、三个seed；E/D/static/adaptive，9组36条策略回放。|
|验证问题|动态规则能否优于静态E/D选择。|
|主要结果|稀疏图D有利；当前adaptive没有超过简单static，degree1反而慢约17.74%。|
|结论边界与异常|已知轨迹生成回放，不是四套完整训练；静态新种子复核仍按既有计划处理。|
|代码状态|本提交有4个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/path_selection/README.md](../../experiments/path_selection/README.md) · [experiments/path_selection/INDEPENDENT_REVIEW.md](../../experiments/path_selection/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/path_selection/results_full/report.md](../../experiments/path_selection/results_full/report.md) · [outputs/path_selection_results_20261030/INDEPENDENT_REVIEW.md](../../outputs/path_selection_results_20261030/INDEPENDENT_REVIEW.md) · [outputs/path_selection_results_20261030/RESULTS_REVIEW.md](../../outputs/path_selection_results_20261030/RESULTS_REVIEW.md)

**归档、清单与原始文件：** [archives/path_selection_raw_records_m4096_d1_seed_404.zip](../../archives/path_selection_raw_records_m4096_d1_seed_404.zip) · [archives/path_selection_raw_records_m4096_d1_seed_505.zip](../../archives/path_selection_raw_records_m4096_d1_seed_505.zip) · [archives/path_selection_raw_records_m4096_d1_seed_606.zip](../../archives/path_selection_raw_records_m4096_d1_seed_606.zip) · [archives/path_selection_raw_records_m4096_d4_seed_404.zip](../../archives/path_selection_raw_records_m4096_d4_seed_404.zip) · [archives/path_selection_raw_records_m4096_d4_seed_505.zip](../../archives/path_selection_raw_records_m4096_d4_seed_505.zip) · [archives/path_selection_raw_records_m4096_d4_seed_606.zip](../../archives/path_selection_raw_records_m4096_d4_seed_606.zip) · [archives/path_selection_raw_records_m4096_d8_seed_404.zip](../../archives/path_selection_raw_records_m4096_d8_seed_404.zip) · [archives/path_selection_raw_records_m4096_d8_seed_505.zip](../../archives/path_selection_raw_records_m4096_d8_seed_505.zip) · [archives/path_selection_raw_records_m4096_d8_seed_606.zip](../../archives/path_selection_raw_records_m4096_d8_seed_606.zip) · [experiments/path_selection/SOURCE_MANIFEST.json](../../experiments/path_selection/SOURCE_MANIFEST.json) · [experiments/path_selection/results_full/completed.json](../../experiments/path_selection/results_full/completed.json)
|E07|[临时聚合者交接与恢复](#e07)|提交状态能否正确交接，复制是否节省累计通信。|[原实验说明](../../experiments/aggregator_recovery/README.md)|

<a id="e07"></a>
## E07 临时聚合者交接与恢复

|项目|记录|
|---|---|
|实验目录|`experiments/aggregator_recovery/`|
|配置与对照|6场景×3seed×rebuild/on_demand/hot_backup，18组54条合成关系回放。|
|验证问题|提交状态能否正确交接，复制是否节省累计通信。|
|主要结果|正确性核验通过；on_demand在线交接总字节约多0.17%，热备多9.3%–23.1%，未支持累计通信优化。|
|结论边界与异常|可靠内存、已知存活名单、原子提交屏障；未接训练模型状态，非真实网络容错。|
|代码状态|本提交有4个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/aggregator_recovery/README.md](../../experiments/aggregator_recovery/README.md) · [experiments/aggregator_recovery/INDEPENDENT_REVIEW.md](../../experiments/aggregator_recovery/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/aggregator_recovery/results_full/report.md](../../experiments/aggregator_recovery/results_full/report.md) · [outputs/aggregator_recovery_results_20261030/INDEPENDENT_REVIEW.md](../../outputs/aggregator_recovery_results_20261030/INDEPENDENT_REVIEW.md) · [outputs/aggregator_recovery_results_20261030/RESULTS_REVIEW.md](../../outputs/aggregator_recovery_results_20261030/RESULTS_REVIEW.md)

**归档、清单与原始文件：** [archives/aggregator_recovery_raw_records_control_sparse_seed_404.zip](../../archives/aggregator_recovery_raw_records_control_sparse_seed_404.zip) · [archives/aggregator_recovery_raw_records_control_sparse_seed_505.zip](../../archives/aggregator_recovery_raw_records_control_sparse_seed_505.zip) · [archives/aggregator_recovery_raw_records_control_sparse_seed_606.zip](../../archives/aggregator_recovery_raw_records_control_sparse_seed_606.zip) · [archives/aggregator_recovery_raw_records_crash_dense_seed_404.zip](../../archives/aggregator_recovery_raw_records_crash_dense_seed_404.zip) · [archives/aggregator_recovery_raw_records_crash_dense_seed_505.zip](../../archives/aggregator_recovery_raw_records_crash_dense_seed_505.zip) · [archives/aggregator_recovery_raw_records_crash_dense_seed_606.zip](../../archives/aggregator_recovery_raw_records_crash_dense_seed_606.zip) · [archives/aggregator_recovery_raw_records_crash_down_sparse_seed_404.zip](../../archives/aggregator_recovery_raw_records_crash_down_sparse_seed_404.zip) · [archives/aggregator_recovery_raw_records_crash_down_sparse_seed_505.zip](../../archives/aggregator_recovery_raw_records_crash_down_sparse_seed_505.zip) · [archives/aggregator_recovery_raw_records_crash_down_sparse_seed_606.zip](../../archives/aggregator_recovery_raw_records_crash_down_sparse_seed_606.zip) · [archives/aggregator_recovery_raw_records_crash_upload_sparse_seed_404.zip](../../archives/aggregator_recovery_raw_records_crash_upload_sparse_seed_404.zip) · [archives/aggregator_recovery_raw_records_crash_upload_sparse_seed_505.zip](../../archives/aggregator_recovery_raw_records_crash_upload_sparse_seed_505.zip) · [archives/aggregator_recovery_raw_records_crash_upload_sparse_seed_606.zip](../../archives/aggregator_recovery_raw_records_crash_upload_sparse_seed_606.zip) · [archives/aggregator_recovery_raw_records_frequent_crash_seed_404.zip](../../archives/aggregator_recovery_raw_records_frequent_crash_seed_404.zip) · [archives/aggregator_recovery_raw_records_frequent_crash_seed_505.zip](../../archives/aggregator_recovery_raw_records_frequent_crash_seed_505.zip) · [archives/aggregator_recovery_raw_records_frequent_crash_seed_606.zip](../../archives/aggregator_recovery_raw_records_frequent_crash_seed_606.zip) · [archives/aggregator_recovery_raw_records_handoff_sparse_seed_404.zip](../../archives/aggregator_recovery_raw_records_handoff_sparse_seed_404.zip) · [archives/aggregator_recovery_raw_records_handoff_sparse_seed_505.zip](../../archives/aggregator_recovery_raw_records_handoff_sparse_seed_505.zip) · [archives/aggregator_recovery_raw_records_handoff_sparse_seed_606.zip](../../archives/aggregator_recovery_raw_records_handoff_sparse_seed_606.zip) · [experiments/aggregator_recovery/SOURCE_MANIFEST.json](../../experiments/aggregator_recovery/SOURCE_MANIFEST.json) · [experiments/aggregator_recovery/results_full/completed.json](../../experiments/aggregator_recovery/results_full/completed.json)
|E08|[类别比例非IID与宽度异构](#e08)|非IID下精确保持、净收益及质量事件。|[原实验说明](../../experiments/noniid_clustering/README.md)|

<a id="e08"></a>
## E08 类别比例非IID与宽度异构

|项目|记录|
|---|---|
|实验目录|`experiments/noniid_clustering/`|
|配置与对照|Fashion-MNIST，IID/α0.5/α0.1、404/505/606、6异宽客户端；9组Local/B/E/D，另36内存回放。|
|验证问题|非IID下精确保持、净收益及质量事件。|
|主要结果|D/B头部9/9更快，中位约4.92%–5.77%；D/E8/9更快；同配置模型和消息一致。|
|结论边界与异常|容量近乎相等，不是数据量不均；协作质量增益不稳定。|
|代码状态|本提交有6个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/noniid_clustering/README.md](../../experiments/noniid_clustering/README.md) · [experiments/noniid_clustering/INDEPENDENT_REVIEW.md](../../experiments/noniid_clustering/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/noniid_clustering/results_full/report.md](../../experiments/noniid_clustering/results_full/report.md)

**归档、清单与原始文件：** [archives/noniid_clustering_raw_records_dirichlet_0.1_seed_404.zip](../../archives/noniid_clustering_raw_records_dirichlet_0.1_seed_404.zip) · [archives/noniid_clustering_raw_records_dirichlet_0.1_seed_505.zip](../../archives/noniid_clustering_raw_records_dirichlet_0.1_seed_505.zip) · [archives/noniid_clustering_raw_records_dirichlet_0.1_seed_606.zip](../../archives/noniid_clustering_raw_records_dirichlet_0.1_seed_606.zip) · [archives/noniid_clustering_raw_records_dirichlet_0.5_seed_404.zip](../../archives/noniid_clustering_raw_records_dirichlet_0.5_seed_404.zip) · [archives/noniid_clustering_raw_records_dirichlet_0.5_seed_505.zip](../../archives/noniid_clustering_raw_records_dirichlet_0.5_seed_505.zip) · [archives/noniid_clustering_raw_records_dirichlet_0.5_seed_606.zip](../../archives/noniid_clustering_raw_records_dirichlet_0.5_seed_606.zip) · [archives/noniid_clustering_raw_records_iid_seed_404.zip](../../archives/noniid_clustering_raw_records_iid_seed_404.zip) · [archives/noniid_clustering_raw_records_iid_seed_505.zip](../../archives/noniid_clustering_raw_records_iid_seed_505.zip) · [archives/noniid_clustering_raw_records_iid_seed_606.zip](../../archives/noniid_clustering_raw_records_iid_seed_606.zip) · [experiments/noniid_clustering/SOURCE_MANIFEST.json](../../experiments/noniid_clustering/SOURCE_MANIFEST.json) · [experiments/noniid_clustering/results_full/completed.json](../../experiments/noniid_clustering/results_full/completed.json)
|E09|[跨客户端知识机制消融](#e09)|区别公共更新、额外计算与正确跨客户端信息的作用。|[原实验说明](../../experiments/collaboration_mechanism/README.md)|

<a id="e09"></a>
## E09 跨客户端知识机制消融

|项目|记录|
|---|---|
|实验目录|`experiments/collaboration_mechanism/`|
|配置与对照|9组Local/Self/Aggregate/Shuffled；公共分支相同更新预算；同快照梯度探针。|
|验证问题|区别公共更新、额外计算与正确跨客户端信息的作用。|
|主要结果|主场景Aggregate相对Self的ACC有利，但相对Shuffled未过主筛查；不能确认稳定全面协作质量提升。|
|结论边界与异常|不同训练分支会分化；同快照反事实与终点分支对照含义不同。计算贡献不以ACC提高为前提。|
|代码状态|本提交有7个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/collaboration_mechanism/README.md](../../experiments/collaboration_mechanism/README.md) · [experiments/collaboration_mechanism/INDEPENDENT_REVIEW.md](../../experiments/collaboration_mechanism/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/collaboration_mechanism/results_full/report.md](../../experiments/collaboration_mechanism/results_full/report.md)

**归档、清单与原始文件：** [archives/collaboration_mechanism_derived_logs.zip](../../archives/collaboration_mechanism_derived_logs.zip) · [archives/collaboration_mechanism_raw_records_dirichlet_0.1_seed_404.zip](../../archives/collaboration_mechanism_raw_records_dirichlet_0.1_seed_404.zip) · [archives/collaboration_mechanism_raw_records_dirichlet_0.1_seed_505.zip](../../archives/collaboration_mechanism_raw_records_dirichlet_0.1_seed_505.zip) · [archives/collaboration_mechanism_raw_records_dirichlet_0.1_seed_606.zip](../../archives/collaboration_mechanism_raw_records_dirichlet_0.1_seed_606.zip) · [archives/collaboration_mechanism_raw_records_dirichlet_0.5_seed_404.zip](../../archives/collaboration_mechanism_raw_records_dirichlet_0.5_seed_404.zip) · [archives/collaboration_mechanism_raw_records_dirichlet_0.5_seed_505.zip](../../archives/collaboration_mechanism_raw_records_dirichlet_0.5_seed_505.zip) · [archives/collaboration_mechanism_raw_records_dirichlet_0.5_seed_606.zip](../../archives/collaboration_mechanism_raw_records_dirichlet_0.5_seed_606.zip) · [archives/collaboration_mechanism_raw_records_iid_seed_404.zip](../../archives/collaboration_mechanism_raw_records_iid_seed_404.zip) · [archives/collaboration_mechanism_raw_records_iid_seed_505.zip](../../archives/collaboration_mechanism_raw_records_iid_seed_505.zip) · [archives/collaboration_mechanism_raw_records_iid_seed_606.zip](../../archives/collaboration_mechanism_raw_records_iid_seed_606.zip) · [experiments/collaboration_mechanism/SOURCE_MANIFEST.json](../../experiments/collaboration_mechanism/SOURCE_MANIFEST.json) · [experiments/collaboration_mechanism/results_full/completed.json](../../experiments/collaboration_mechanism/results_full/completed.json)
|E10|[固定公共学生预算](#e10)|隔离原先公共库增大同时增加学生训练预算的混杂。|[原实验说明](../../experiments/public_budget/README.md)|

<a id="e10"></a>
## E10 固定公共学生预算

|项目|记录|
|---|---|
|实验目录|`experiments/public_budget/`|
|配置与对照|Fashion-MNIST，IID/α0.1，404/505/606；M4096完整8步、M16384完整32步/固定8步；18组54方法+18内存回放。|
|验证问题|隔离原先公共库增大同时增加学生训练预算的混杂。|
|主要结果|暂停共同掩码后，大M固定8步D/B头部省13.44%/15.12%，D/E省−1.32%/3.19%（IID/强非IID）；六配置平均ACC预算护栏通过。|
|结论边界与异常|用户确认的两次手动暂停不算故障；仅按共同轮掩码处理该批记录，不推广至其他实验。|
|代码状态|本提交有7个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/public_budget/README.md](../../experiments/public_budget/README.md) · [experiments/public_budget/INDEPENDENT_REVIEW.md](../../experiments/public_budget/INDEPENDENT_REVIEW.md)

**结果与审核：** [experiments/public_budget/results_full/report.md](../../experiments/public_budget/results_full/report.md) · [outputs/public_budget_results_20261031/INDEPENDENT_REVIEW.md](../../outputs/public_budget_results_20261031/INDEPENDENT_REVIEW.md) · [outputs/public_budget_results_20261031/RESULTS_REVIEW.md](../../outputs/public_budget_results_20261031/RESULTS_REVIEW.md) · [outputs/public_budget_results_20261031/pause_adjusted/report.md](../../outputs/public_budget_results_20261031/pause_adjusted/report.md)

**归档、清单与原始文件：** [archives/public_budget_derived_logs.zip](../../archives/public_budget_derived_logs.zip) · [archives/public_budget_pause_adjusted_summary.zip](../../archives/public_budget_pause_adjusted_summary.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m16384_fixed8_seed_404.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m16384_fixed8_seed_404.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m16384_fixed8_seed_505.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m16384_fixed8_seed_505.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m16384_fixed8_seed_606.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m16384_fixed8_seed_606.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m16384_full_seed_404.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m16384_full_seed_404.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m16384_full_seed_505.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m16384_full_seed_505.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m16384_full_seed_606.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m16384_full_seed_606.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m4096_full_seed_404.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m4096_full_seed_404.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m4096_full_seed_505.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m4096_full_seed_505.zip) · [archives/public_budget_raw_records_dirichlet_0.1_m4096_full_seed_606.zip](../../archives/public_budget_raw_records_dirichlet_0.1_m4096_full_seed_606.zip) · [archives/public_budget_raw_records_iid_m16384_fixed8_seed_404.zip](../../archives/public_budget_raw_records_iid_m16384_fixed8_seed_404.zip) · [archives/public_budget_raw_records_iid_m16384_fixed8_seed_505.zip](../../archives/public_budget_raw_records_iid_m16384_fixed8_seed_505.zip) · [archives/public_budget_raw_records_iid_m16384_fixed8_seed_606.zip](../../archives/public_budget_raw_records_iid_m16384_fixed8_seed_606.zip) · [archives/public_budget_raw_records_iid_m16384_full_seed_404.zip](../../archives/public_budget_raw_records_iid_m16384_full_seed_404.zip) · [archives/public_budget_raw_records_iid_m16384_full_seed_505.zip](../../archives/public_budget_raw_records_iid_m16384_full_seed_505.zip) · [archives/public_budget_raw_records_iid_m16384_full_seed_606.zip](../../archives/public_budget_raw_records_iid_m16384_full_seed_606.zip) · [archives/public_budget_raw_records_iid_m4096_full_seed_404.zip](../../archives/public_budget_raw_records_iid_m4096_full_seed_404.zip) · [archives/public_budget_raw_records_iid_m4096_full_seed_505.zip](../../archives/public_budget_raw_records_iid_m4096_full_seed_505.zip) · [archives/public_budget_raw_records_iid_m4096_full_seed_606.zip](../../archives/public_budget_raw_records_iid_m4096_full_seed_606.zip) · [experiments/public_budget/SOURCE_MANIFEST.json](../../experiments/public_budget/SOURCE_MANIFEST.json) · [experiments/public_budget/results_full/completed.json](../../experiments/public_budget/results_full/completed.json)
|E11|[私有头部工作负载](#e11)|私有训练占比下降时认证的完整头部收益。|[原实验说明](../../experiments/private_workload/README.md)|

<a id="e11"></a>
## E11 私有头部工作负载

|项目|记录|
|---|---|
|实验目录|`experiments/private_workload/`|
|配置与对照|完整/2048/1024私有样本预算，M16384固定公共8步；三seed两划分B/E/D，18case。|
|验证问题|私有训练占比下降时认证的完整头部收益。|
|主要结果|2048较有利但强非IID seed404质量护栏失败；1024六配置全部超1个百分点护栏，不采用。|
|结论边界与异常|只减少私有头部工作量，AE仍全量准备；减预算省时不属于认证贡献。|
|代码状态|本提交有8个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/private_workload/README.md](../../experiments/private_workload/README.md) · [experiments/private_workload/VALIDATION.md](../../experiments/private_workload/VALIDATION.md)

**结果与审核：** [experiments/private_workload/results_full/report.md](../../experiments/private_workload/results_full/report.md) · [outputs/private_workload_results_20261031/RESULTS_REVIEW.md](../../outputs/private_workload_results_20261031/RESULTS_REVIEW.md) · [outputs/private_workload_results_20261031/independent_review.md](../../outputs/private_workload_results_20261031/independent_review.md) · [outputs/private_workload_results_20261031/pause_adjusted/report.md](../../outputs/private_workload_results_20261031/pause_adjusted/report.md) · [outputs/private_workload_review_20261031/INDEPENDENT_REVIEW.md](../../outputs/private_workload_review_20261031/INDEPENDENT_REVIEW.md) · [outputs/private_workload_review_20261031/LOCAL_REVIEW.md](../../outputs/private_workload_review_20261031/LOCAL_REVIEW.md)

**归档、清单与原始文件：** [archives/private_workload_derived.zip](../../archives/private_workload_derived.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv1024_seed_404.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv1024_seed_404.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv1024_seed_505.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv1024_seed_505.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv1024_seed_606.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv1024_seed_606.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv2048_seed_404.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv2048_seed_404.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv2048_seed_505.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv2048_seed_505.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv2048_seed_606.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_priv2048_seed_606.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_privfull_seed_404.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_privfull_seed_404.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_privfull_seed_505.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_privfull_seed_505.zip) · [archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_privfull_seed_606.zip](../../archives/private_workload_raw_dirichlet_0.1_m16384_fixed8_privfull_seed_606.zip) · [archives/private_workload_raw_iid_m16384_fixed8_priv1024_seed_404.zip](../../archives/private_workload_raw_iid_m16384_fixed8_priv1024_seed_404.zip) · [archives/private_workload_raw_iid_m16384_fixed8_priv1024_seed_505.zip](../../archives/private_workload_raw_iid_m16384_fixed8_priv1024_seed_505.zip) · [archives/private_workload_raw_iid_m16384_fixed8_priv1024_seed_606.zip](../../archives/private_workload_raw_iid_m16384_fixed8_priv1024_seed_606.zip) · [archives/private_workload_raw_iid_m16384_fixed8_priv2048_seed_404.zip](../../archives/private_workload_raw_iid_m16384_fixed8_priv2048_seed_404.zip) · [archives/private_workload_raw_iid_m16384_fixed8_priv2048_seed_505.zip](../../archives/private_workload_raw_iid_m16384_fixed8_priv2048_seed_505.zip) · [archives/private_workload_raw_iid_m16384_fixed8_priv2048_seed_606.zip](../../archives/private_workload_raw_iid_m16384_fixed8_priv2048_seed_606.zip) · [archives/private_workload_raw_iid_m16384_fixed8_privfull_seed_404.zip](../../archives/private_workload_raw_iid_m16384_fixed8_privfull_seed_404.zip) · [archives/private_workload_raw_iid_m16384_fixed8_privfull_seed_505.zip](../../archives/private_workload_raw_iid_m16384_fixed8_privfull_seed_505.zip) · [archives/private_workload_raw_iid_m16384_fixed8_privfull_seed_606.zip](../../archives/private_workload_raw_iid_m16384_fixed8_privfull_seed_606.zip) · [experiments/private_workload/results_full/completed.json](../../experiments/private_workload/results_full/completed.json)
|E12|[独立进程性能确认与插电补测](#e12)|微小D/E收益能否在独立进程复现，并披露运行噪声。|[原实验说明](../../experiments/perf_confirmation/README.md)|

<a id="e12"></a>
## E12 独立进程性能确认与插电补测

|项目|记录|
|---|---|
|实验目录|`experiments/perf_confirmation/`|
|配置与对照|新seed707/808/909、完整/2048、两划分B/E/D；原计划72次，后按明确补测规则汇总。|
|验证问题|微小D/E收益能否在独立进程复现，并披露运行噪声。|
|主要结果|插电补测后2048档IID/强非IID头部D/B省24.28%/22.61%，D/E省5.73%/6.52%。|
|结论边界与异常|当前66次保留原运行+6次补测，seed重复数不等，属事后汇总，不能冒充原始预注册确认；异常和电池诊断原记录保留。|
|代码状态|本提交有6个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/perf_confirmation/README.md](../../experiments/perf_confirmation/README.md) · [experiments/perf_confirmation/PREREGISTRATION.md](../../experiments/perf_confirmation/PREREGISTRATION.md) · [experiments/perf_confirmation/VALIDATION.md](../../experiments/perf_confirmation/VALIDATION.md)

**结果与审核：** [experiments/perf_confirmation/results_full/CURRENT_RESULTS.md](../../experiments/perf_confirmation/results_full/CURRENT_RESULTS.md) · [experiments/perf_confirmation/results_full/report.md](../../experiments/perf_confirmation/results_full/report.md) · [outputs/perf_confirmation_results_20261101/INDEPENDENT_REVIEW.md](../../outputs/perf_confirmation_results_20261101/INDEPENDENT_REVIEW.md) · [outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md](../../outputs/perf_confirmation_results_20261101/RESULTS_REVIEW.md)

**归档、清单与原始文件：** [archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_priv2048_seed_707.zip](../../archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_priv2048_seed_707.zip) · [archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_priv2048_seed_808.zip](../../archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_priv2048_seed_808.zip) · [archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_priv2048_seed_909.zip](../../archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_priv2048_seed_909.zip) · [archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_privfull_seed_707.zip](../../archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_privfull_seed_707.zip) · [archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_privfull_seed_808.zip](../../archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_privfull_seed_808.zip) · [archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_privfull_seed_909.zip](../../archives/perf_confirmation_dirichlet_0.1_m16384_fixed8_privfull_seed_909.zip) · [archives/perf_confirmation_iid_m16384_fixed8_priv2048_seed_707.zip](../../archives/perf_confirmation_iid_m16384_fixed8_priv2048_seed_707.zip) · [archives/perf_confirmation_iid_m16384_fixed8_priv2048_seed_808.zip](../../archives/perf_confirmation_iid_m16384_fixed8_priv2048_seed_808.zip) · [archives/perf_confirmation_iid_m16384_fixed8_priv2048_seed_909.zip](../../archives/perf_confirmation_iid_m16384_fixed8_priv2048_seed_909.zip) · [archives/perf_confirmation_iid_m16384_fixed8_privfull_seed_707.zip](../../archives/perf_confirmation_iid_m16384_fixed8_privfull_seed_707.zip) · [archives/perf_confirmation_iid_m16384_fixed8_privfull_seed_808.zip](../../archives/perf_confirmation_iid_m16384_fixed8_privfull_seed_808.zip) · [archives/perf_confirmation_iid_m16384_fixed8_privfull_seed_909.zip](../../archives/perf_confirmation_iid_m16384_fixed8_privfull_seed_909.zip) · [archives/perf_confirmation_normal_rerun_20261101.zip](../../archives/perf_confirmation_normal_rerun_20261101.zip) · [archives/perf_confirmation_rerun_20261101.zip](../../archives/perf_confirmation_rerun_20261101.zip) · [experiments/perf_confirmation/results_full/completed.json](../../experiments/perf_confirmation/results_full/completed.json)
|E13|[STL-10首轮迁移](#e13)|自然彩色图像与不同公共数据源下的计算迁移。|[原实验说明](../../experiments/stl10_transfer/README.md)|

<a id="e13"></a>
## E13 STL-10首轮迁移

|项目|记录|
|---|---|
|实验目录|`experiments/stl10_transfer/`|
|配置与对照|3seed×IID/α0.1×M4096/16384×B/E/D=36次200轮运行；公共8步。|
|验证问题|自然彩色图像与不同公共数据源下的计算迁移。|
|主要结果|关系、参数与评估保持一致；但12配置全部严重退化，不能作为有效聚类质量下的成功迁移。|
|结论边界与异常|认证精确不等于基础学习目标健康；生成省算不能掩盖单簇。|
|代码状态|本提交有8个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/stl10_transfer/README.md](../../experiments/stl10_transfer/README.md) · [experiments/stl10_transfer/PREREGISTRATION.md](../../experiments/stl10_transfer/PREREGISTRATION.md) · [experiments/stl10_transfer/VALIDATION.md](../../experiments/stl10_transfer/VALIDATION.md)

**结果与审核：** [experiments/stl10_transfer/results_full/report.md](../../experiments/stl10_transfer/results_full/report.md) · [outputs/stl10_transfer_results_20261101/COLLAPSE_ANALYSIS.md](../../outputs/stl10_transfer_results_20261101/COLLAPSE_ANALYSIS.md) · [outputs/stl10_transfer_results_20261101/DIAGNOSTIC_PLAN.md](../../outputs/stl10_transfer_results_20261101/DIAGNOSTIC_PLAN.md) · [outputs/stl10_transfer_results_20261101/INDEPENDENT_REVIEW.md](../../outputs/stl10_transfer_results_20261101/INDEPENDENT_REVIEW.md) · [outputs/stl10_transfer_results_20261101/REVIEW.md](../../outputs/stl10_transfer_results_20261101/REVIEW.md) · [outputs/stl10_transfer_setup_20261101/INDEPENDENT_REVIEW.md](../../outputs/stl10_transfer_setup_20261101/INDEPENDENT_REVIEW.md)

**归档、清单与原始文件：** [archives/stl10_transfer_seed1001_20261101.zip](../../archives/stl10_transfer_seed1001_20261101.zip) · [archives/stl10_transfer_seed1002_20261101.zip](../../archives/stl10_transfer_seed1002_20261101.zip) · [archives/stl10_transfer_seed1003_20261101.zip](../../archives/stl10_transfer_seed1003_20261101.zip) · [experiments/stl10_transfer/results_full/completed.json](../../experiments/stl10_transfer/results_full/completed.json)
|E14|[STL-10退化三分支定位](#e14)|定位私有训练、公共更新与动态反馈的影响。|[原实验说明](../../experiments/stl10_diagnostics/README.md)|

<a id="e14"></a>
## E14 STL-10退化三分支定位

|项目|记录|
|---|---|
|实验目录|`experiments/stl10_diagnostics/`|
|配置与对照|seed1001、IID、M16384、40轮；P仅私有、J原联合、F固定首轮目标。|
|验证问题|定位私有训练、公共更新与动态反馈的影响。|
|主要结果|40轮P为0/6单簇、J为6/6、F为3/6，支持公共更新与反馈参与退化的解释。|
|结论边界与异常|单seed单划分；冻结目标仍退化，不能将全部原因归为动态反馈。|
|代码状态|本提交有5个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/stl10_diagnostics/README.md](../../experiments/stl10_diagnostics/README.md) · [experiments/stl10_diagnostics/VALIDATION.md](../../experiments/stl10_diagnostics/VALIDATION.md)

**结果与审核：** [experiments/stl10_diagnostics/results_full/report.md](../../experiments/stl10_diagnostics/results_full/report.md) · [outputs/stl10_diagnostics_results_20261101/REVIEW.md](../../outputs/stl10_diagnostics_results_20261101/REVIEW.md) · [outputs/stl10_diagnostics_setup_20261101/INDEPENDENT_REVIEW.md](../../outputs/stl10_diagnostics_setup_20261101/INDEPENDENT_REVIEW.md)

**归档、清单与原始文件：** [archives/stl10_diagnostics_raw_20261101.zip](../../archives/stl10_diagnostics_raw_20261101.zip) · [experiments/stl10_diagnostics/results_full/completed.json](../../experiments/stl10_diagnostics/results_full/completed.json)
|E15|[公共步数剂量诊断](#e15)|只减少公共更新预算能否缓解退化。|[原实验说明](../../experiments/stl10_public_steps/README.md)|

<a id="e15"></a>
## E15 公共步数剂量诊断

|项目|记录|
|---|---|
|实验目录|`experiments/stl10_public_steps/`|
|配置与对照|相同私有7步，公共1/2/4/8步；seed1001、IID、40轮。|
|验证问题|只减少公共更新预算能否缓解退化。|
|主要结果|1/2步末轮未单簇；4步存在瞬时单簇并部分恢复；8步全部单簇。|
|结论边界与异常|短程探索，不是长程保证；步数改变也改变公共信息消费量。|
|代码状态|本提交有3个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/stl10_public_steps/README.md](../../experiments/stl10_public_steps/README.md) · [experiments/stl10_public_steps/VALIDATION.md](../../experiments/stl10_public_steps/VALIDATION.md)

**结果与审核：** [experiments/stl10_public_steps/results_full/report.md](../../experiments/stl10_public_steps/results_full/report.md) · [outputs/stl10_public_steps_results_20261101/REVIEW.md](../../outputs/stl10_public_steps_results_20261101/REVIEW.md) · [outputs/stl10_public_steps_setup_20261101/INDEPENDENT_REVIEW.md](../../outputs/stl10_public_steps_setup_20261101/INDEPENDENT_REVIEW.md)

**归档、清单与原始文件：** [archives/stl10_public_steps_raw_20261101.zip](../../archives/stl10_public_steps_raw_20261101.zip) · [experiments/stl10_public_steps/results_full/completed.json](../../experiments/stl10_public_steps/results_full/completed.json)
|E16|[公共1/2步长程确认](#e16)|低公共预算在长程和新seed/非IID下是否仍通过退化护栏。|[原实验说明](../../experiments/stl10_longrun/README.md)|

<a id="e16"></a>
## E16 公共1/2步长程确认

|项目|记录|
|---|---|
|实验目录|`experiments/stl10_longrun/`|
|配置与对照|1/2步×未参与剂量选档seed1002/1003×IID/α0.1；8条B轨迹各200轮。|
|验证问题|低公共预算在长程和新seed/非IID下是否仍通过退化护栏。|
|主要结果|8条均通过冻结S1/S2/Q1/Q2，按预先规则选择2步。|
|结论边界与异常|仍记录早期短暂集中；仅B质量选档，不产生认证省时结论。|
|代码状态|本提交有6个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/stl10_longrun/README.md](../../experiments/stl10_longrun/README.md) · [experiments/stl10_longrun/PREREGISTRATION.md](../../experiments/stl10_longrun/PREREGISTRATION.md) · [experiments/stl10_longrun/VALIDATION.md](../../experiments/stl10_longrun/VALIDATION.md)

**结果与审核：** [experiments/stl10_longrun/results_full/report.md](../../experiments/stl10_longrun/results_full/report.md) · [outputs/stl10_longrun_results_20261101/REVIEW.md](../../outputs/stl10_longrun_results_20261101/REVIEW.md) · [outputs/stl10_longrun_review_20261101/REVIEW.md](../../outputs/stl10_longrun_review_20261101/REVIEW.md)

**归档、清单与原始文件：** [archives/stl10_longrun_raw_20261101.manifest.json](../../archives/stl10_longrun_raw_20261101.manifest.json) · [archives/stl10_longrun_raw_20261101.zip](../../archives/stl10_longrun_raw_20261101.zip) · [experiments/stl10_longrun/results_full/completed.json](../../experiments/stl10_longrun/results_full/completed.json)
|E17|[固定2步计算迁移](#e17)|在固定健康公共预算下重新比较认证成本。|[原实验说明](../../experiments/stl10_compute/README.md)|

<a id="e17"></a>
## E17 固定2步计算迁移

|项目|记录|
|---|---|
|实验目录|`experiments/stl10_compute/`|
|配置与对照|两划分×1001/1002/1003×B/E/D=18独立进程，M16384、200轮。|
|验证问题|在固定健康公共预算下重新比较认证成本。|
|主要结果|6三元组精确一致且质量通过；D/B头部中位省38.56%/35.47%，D/E省16.65%/9.46%。|
|结论边界与异常|每方法一次，属探索；8降2的预算节省不算认证功劳。|
|代码状态|本提交有5个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/stl10_compute/README.md](../../experiments/stl10_compute/README.md) · [experiments/stl10_compute/PREREGISTRATION.md](../../experiments/stl10_compute/PREREGISTRATION.md) · [experiments/stl10_compute/VALIDATION.md](../../experiments/stl10_compute/VALIDATION.md)

**结果与审核：** [experiments/stl10_compute/results_full/report.md](../../experiments/stl10_compute/results_full/report.md) · [outputs/stl10_compute_results_20261101/REVIEW.md](../../outputs/stl10_compute_results_20261101/REVIEW.md) · [outputs/stl10_compute_review_20261101/REVIEW.md](../../outputs/stl10_compute_review_20261101/REVIEW.md)

**归档、清单与原始文件：** [archives/stl10_compute_raw_20261101.manifest.json](../../archives/stl10_compute_raw_20261101.manifest.json) · [archives/stl10_compute_seed1001_raw_records_20261101.zip](../../archives/stl10_compute_seed1001_raw_records_20261101.zip) · [archives/stl10_compute_seed1002_raw_records_20261101.zip](../../archives/stl10_compute_seed1002_raw_records_20261101.zip) · [archives/stl10_compute_seed1003_raw_records_20261101.zip](../../archives/stl10_compute_seed1003_raw_records_20261101.zip) · [experiments/stl10_compute/results_full/completed.json](../../experiments/stl10_compute/results_full/completed.json)
|E18|[STL-10固定轨迹重复计时](#e18)|已有配置下方向与判定是否复现。|[原实验说明](../../experiments/stl10_repeat_confirmation/README.md)|

<a id="e18"></a>
## E18 STL-10固定轨迹重复计时

|项目|记录|
|---|---|
|实验目录|`experiments/stl10_repeat_confirmation/`|
|配置与对照|6配置×B/E/D×3技术重复=54独立进程；重复先在seed内平均。|
|验证问题|已有配置下方向与判定是否复现。|
|主要结果|IID D/B省38.79%、D/E10.71%；强非IID39.53%/11.09%，两划分C1/C2/C3通过。|
|结论边界与异常|固定旧seed，非新随机实例；存在较大重复波动，不等于排除全部机器噪声。|
|代码状态|本提交有5个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/stl10_repeat_confirmation/README.md](../../experiments/stl10_repeat_confirmation/README.md) · [experiments/stl10_repeat_confirmation/PREREGISTRATION.md](../../experiments/stl10_repeat_confirmation/PREREGISTRATION.md) · [experiments/stl10_repeat_confirmation/VALIDATION.md](../../experiments/stl10_repeat_confirmation/VALIDATION.md)

**结果与审核：** [experiments/stl10_repeat_confirmation/results_full/report.md](../../experiments/stl10_repeat_confirmation/results_full/report.md)

**归档、清单与原始文件：** [experiments/stl10_repeat_confirmation/results_full/completed.json](../../experiments/stl10_repeat_confirmation/results_full/completed.json)
|E19|[输出簇数K边界](#e19)|K增长时认证维护与空间成本是否抵消省算。|[原实验说明](../../experiments/k_scaling/README.md)|

<a id="e19"></a>
## E19 输出簇数K边界

|项目|记录|
|---|---|
|实验目录|`experiments/k_scaling/`|
|配置与对照|K10/16/32/64×两划分×三seed×B/E/D=72次，另12隔离内存回放。|
|验证问题|K增长时认证维护与空间成本是否抵消省算。|
|主要结果|D/B24/24更快；K64 D/E强非IID中位慢1.47%，seed1002的6客户端全单簇。|
|结论边界与异常|真类仍10，K变更也改变私有伪标签；受休眠污染的准备成本标NA，方法计时不剔除。|
|代码状态|本提交有7个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/k_scaling/README.md](../../experiments/k_scaling/README.md) · [experiments/k_scaling/PREREGISTRATION.md](../../experiments/k_scaling/PREREGISTRATION.md) · [experiments/k_scaling/VALIDATION.md](../../experiments/k_scaling/VALIDATION.md)

**结果与审核：** [experiments/k_scaling/results_full/report.md](../../experiments/k_scaling/results_full/report.md) · [outputs/k_scaling_results_20261102/REVIEW.md](../../outputs/k_scaling_results_20261102/REVIEW.md) · [outputs/k_scaling_review_20261102/REVIEW.md](../../outputs/k_scaling_review_20261102/REVIEW.md) · [outputs/k_scaling_sleep_review_20261102/REVIEW.md](../../outputs/k_scaling_sleep_review_20261102/REVIEW.md) · [outputs/k_scaling_sleep_review_20261102/sleep_adjusted/report.md](../../outputs/k_scaling_sleep_review_20261102/sleep_adjusted/report.md)

**归档、清单与原始文件：** [archives/k_scaling_raw_20261102.manifest.json](../../archives/k_scaling_raw_20261102.manifest.json) · [archives/k_scaling_seed1001_raw_records_20261102.zip](../../archives/k_scaling_seed1001_raw_records_20261102.zip) · [archives/k_scaling_seed1002_raw_records_20261102.zip](../../archives/k_scaling_seed1002_raw_records_20261102.zip) · [archives/k_scaling_seed1003_raw_records_20261102.zip](../../archives/k_scaling_seed1003_raw_records_20261102.zip) · [experiments/k_scaling/results_full/completed.json](../../experiments/k_scaling/results_full/completed.json)
|E20|[客户端数量：固定总量](#e20)|客户端增长时计算、通信、内存和退化边界。|[原实验说明](../../experiments/client_scaling/README.md)|

<a id="e20"></a>
## E20 客户端数量：固定总量

|项目|记录|
|---|---|
|实验目录|`experiments/client_scaling/`|
|配置与对照|私有总量5000，N2/6/12×两划分×三seed×B/E/D=54次，另12内存回放。|
|验证问题|客户端增长时计算、通信、内存和退化边界。|
|主要结果|D/B18/18更快；N12强非IID D/E三seed均慢，中位慢10.09%；seed1003末轮3客户端近单簇。|
|结论边界与异常|固定每客户端400分支不能当作已完成；不是私有数量不均实验。|
|代码状态|本提交有8个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/client_scaling/README.md](../../experiments/client_scaling/README.md) · [experiments/client_scaling/PREREGISTRATION.md](../../experiments/client_scaling/PREREGISTRATION.md) · [experiments/client_scaling/VALIDATION.md](../../experiments/client_scaling/VALIDATION.md)

**结果与审核：** [experiments/client_scaling/results_full_fixed_total/report.md](../../experiments/client_scaling/results_full_fixed_total/report.md) · [outputs/client_scaling_results_20261105/REVIEW.md](../../outputs/client_scaling_results_20261105/REVIEW.md)

**归档、清单与原始文件：** [archives/client_scaling_fixed_total_raw_20261105.manifest.json](../../archives/client_scaling_fixed_total_raw_20261105.manifest.json) · [archives/client_scaling_fixed_total_seed1001_raw_20261105.zip](../../archives/client_scaling_fixed_total_seed1001_raw_20261105.zip) · [archives/client_scaling_fixed_total_seed1002_raw_20261105.zip](../../archives/client_scaling_fixed_total_seed1002_raw_20261105.zip) · [archives/client_scaling_fixed_total_seed1003_raw_20261105.zip](../../archives/client_scaling_fixed_total_seed1003_raw_20261105.zip) · [experiments/client_scaling/results_full_fixed_total/completed.json](../../experiments/client_scaling/results_full_fixed_total/completed.json)
|E21|[单簇干预与公共更新强度](#e21)|公共更新过强是否参与维持和放大退化。|[原实验说明](../../experiments/collapse_intervention/README.md)|

<a id="e21"></a>
## E21 单簇干预与公共更新强度

|项目|记录|
|---|---|
|实验目录|`experiments/collapse_intervention/`|
|配置与对照|N12/K10/α0.1/1003；private-only、公共1步、公共2步但有效lr0.05，200轮。|
|验证问题|公共更新过强是否参与维持和放大退化。|
|主要结果|末轮平均最大簇占比约33.26%/34.96%/35.00%，相较原2步lr0.1的96.24%恢复。|
|结论边界与异常|早期集中也见于仅私有分支，不能把初始集中全部归为公共更新。|
|代码状态|本提交有5个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/collapse_intervention/README.md](../../experiments/collapse_intervention/README.md) · [experiments/collapse_intervention/PREREGISTRATION.md](../../experiments/collapse_intervention/PREREGISTRATION.md) · [experiments/collapse_intervention/VALIDATION.md](../../experiments/collapse_intervention/VALIDATION.md)

**结果与审核：** [experiments/collapse_intervention/results_full/report.md](../../experiments/collapse_intervention/results_full/report.md) · [outputs/collapse_intervention_results_20261106/REVIEW.md](../../outputs/collapse_intervention_results_20261106/REVIEW.md)

**归档、清单与原始文件：** [archives/collapse_intervention_raw_20261106.zip](../../archives/collapse_intervention_raw_20261106.zip) · [experiments/collapse_intervention/results_full/completed.json](../../experiments/collapse_intervention/results_full/completed.json)
|E22|[公共学习率0.05确认](#e22)|不改公共边数与步数，仅减更新强度是否可恢复并维持健康配置。|[原实验说明](../../experiments/public_lr_confirmation/README.md)|

<a id="e22"></a>
## E22 公共学习率0.05确认

|项目|记录|
|---|---|
|实验目录|`experiments/public_lr_confirmation/`|
|配置与对照|8配置对照0.1/0.05，16记录含11新增+5历史；N12/K10及N6/K64，新增seed1101。|
|验证问题|不改公共边数与步数，仅减更新强度是否可恢复并维持健康配置。|
|主要结果|0.05全部8配置通过结构/过程/NMI护栏，5项适用ACC副作用护栏通过；0.1为5/8通过。|
|结论边界与异常|新增随机seed只有1101；不是普适防坍缩定理，也不保证每客户端ACC提高。|
|代码状态|本提交有6个Python文件。保持冻结版本与原路径，见代码台账。|

**原始说明及协议：** [experiments/public_lr_confirmation/README.md](../../experiments/public_lr_confirmation/README.md) · [experiments/public_lr_confirmation/PREREGISTRATION.md](../../experiments/public_lr_confirmation/PREREGISTRATION.md) · [experiments/public_lr_confirmation/VALIDATION.md](../../experiments/public_lr_confirmation/VALIDATION.md)

**结果与审核：** [experiments/public_lr_confirmation/results_full/report.md](../../experiments/public_lr_confirmation/results_full/report.md) · [outputs/public_lr_confirmation_results_20261106/REVIEW.md](../../outputs/public_lr_confirmation_results_20261106/REVIEW.md)

**归档、清单与原始文件：** [experiments/public_lr_confirmation/results_full/completed.json](../../experiments/public_lr_confirmation/results_full/completed.json)

|E23|[0.05下同配置计算与内存验证](#e23)|质量轨迹恢复后认证有无净计算收益|[正式报告](../../experiments/lr_compute/results_full/report.md)|

<a id="e23"></a>
## E23 0.05下同配置计算与内存验证

|项目|记录|
|---|---|
|实验目录|`experiments/lr_compute/`|
|配置与对照|8配置×B/E/D，24主运行+6隔离内存，200轮|
|验证问题|质量轨迹恢复后认证有无净计算收益|
|主要结果|D/B8/8更快，D/E7/8更快；关系353,894,400次零错误|
|结论边界与异常|一次/方法；K64/IID/1101慢0.33%，两配置内存代价与准备NA保留|
|代码状态|5个Python文件保持原版与路径，依赖既有冻结核心和缓存|

**原始说明及协议：** [README](../../experiments/lr_compute/README.md) · [预注册](../../experiments/lr_compute/PREREGISTRATION.md) · [开发验证](../../experiments/lr_compute/VALIDATION.md)

**结果与审核：** [正式报告](../../experiments/lr_compute/results_full/report.md) · [审核](../../outputs/lr_compute_results_20261106/REVIEW.md) · [完成清单](../../experiments/lr_compute/results_full/completed.json)

**归档、清单与原始文件：** [60份主运行恢复路径和SHA](../../archives/lr_followups_raw_20261109.manifest.json)；内存原记录在专门ZIP内，电源直接保留。 [发布状态](LOCAL_FOLLOWUPS.md)

|E24|[0.05固定配置技术重复](#e24)|同轨迹下D/B与D/E完整头部收益及机器波动|[正式报告](../../experiments/lr_repeat/results_full/report.md)|

<a id="e24"></a>
## E24 0.05固定配置技术重复

|项目|记录|
|---|---|
|实验目录|`experiments/lr_repeat/`|
|配置与对照|4强非IID配置×B/E/D×3，36独立进程，200轮|
|验证问题|同轨迹下D/B与D/E完整头部收益及机器波动|
|主要结果|D/B中位省25.93%–40.87%；D/E省0.79%–8.47%，C2及合取仅1/4通过|
|结论边界与异常|技术重复不增加seed；不覆盖IID负收益；零剔除，准备污染NA|
|代码状态|5个Python文件保持原版与路径，依赖既有冻结核心和缓存|

**原始说明及协议：** [README](../../experiments/lr_repeat/README.md) · [预注册](../../experiments/lr_repeat/PREREGISTRATION.md) · [开发验证](../../experiments/lr_repeat/VALIDATION.md)

**结果与审核：** [正式报告](../../experiments/lr_repeat/results_full/report.md) · [审核](../../outputs/lr_repeat_results_20261109/REVIEW.md) · [完成清单](../../experiments/lr_repeat/results_full/completed.json)

**归档、清单与原始文件：** [60份主运行恢复路径和SHA](../../archives/lr_followups_raw_20261109.manifest.json)；内存原记录在专门ZIP内，电源直接保留。 [发布状态](LOCAL_FOLLOWUPS.md)



|E25|[0.05固定每客户端400张规模](#e25)|客户端数增大时的精确性、计算与空间边界|[正式报告](../../experiments/lr_client_scaling/results_full_fixed_per_client/report.md)|

<a id="e25"></a>
## E25 0.05固定每客户端400张规模

|项目|记录|
|---|---|
|实验目录|`experiments/lr_client_scaling/`|
|配置与对照|STL-10、N2/6/12、IID/α0.1、seed1001/1002/1003；54主+12内存；K10、公共2步、有效LR0.05、200轮|
|验证问题|固定每客户端400张时，关系认证随规模增长是否仍有净计算收益|
|主要结果|P3固定每客户端400张规模实验已完成：54次主运行+12次隔离内存回放；18/18配置D/B与D/E完整头部均更快，六组配对中位省时分别35.39%–43.57%和6.27%–16.53%。末轮18/18无严重退化，9/18早期配置在20/40轮曾有单簇或≥99%事件。相对B的峰值内存增加9.8%–26.2%，通信字节相同。|
|正确性|18份缓存/102完成文件/90冻结来源均通过；589,824,000关系和786,432,000候选检查零错；12报表重生成一致|
|结论边界与异常|单方法单次、旧种子；跨N同时改变总数据/总模型/公共总步数。关闭PyCharm后resume，15条主记录保留，未完成方法重跑；无计时剔除。两日志间154秒未采样，不算故障或推定休眠。|
|代码状态|5个Python文件保持原版，旧依赖及历史结果不改|

**原始说明及协议：** [README](../../experiments/lr_client_scaling/README.md) · [预注册](../../experiments/lr_client_scaling/PREREGISTRATION.md) · [开发验证](../../experiments/lr_client_scaling/VALIDATION.md)

**结果与审核：** [正式报告](../../experiments/lr_client_scaling/results_full_fixed_per_client/report.md) · [主审](../../outputs/lr_client_scaling_results_20261110/REVIEW.md) · [独立复审](../../outputs/lr_client_scaling_results_20261110/INDEPENDENT_REVIEW.md) · [机器审计](../../outputs/lr_client_scaling_results_20261110/audit.json)

**归档、清单与原始文件：** [66份主/内存记录无损ZIP及恢复路径](../../archives/lr_client_scaling_raw_20261110.manifest.json) · [完成清单](../../experiments/lr_client_scaling/results_full_fixed_per_client/completed.json)。输入指针、电源、环境与小报表直接保留，数据/编码器/特征缓存不上传。


|E26|[私有数量异构](#e26)|数量不均下的认证成本与退化边界|[原报告](../../experiments/quantity_heterogeneity/results_full/report.md)|

<a id="e26"></a>
## E26 私有数量异构

|项目|记录|
|---|---|
|实验目录|`experiments/quantity_heterogeneity/`|
|配置与对照|N6、总2400、equal/moderate/strong、两划分、三旧seed、54主+6strong内存；K10/公共2步/LR0.05/200轮|
|验证问题|数量不均下的同轨迹计算收益与适用范围|
|主要结果|私有数量异构54主+6内存已完成：D/B18/18更快、D/E16/18更快；两个IID/seed1002负收益保留。末轮严重退化equal0/6、moderate2/6、strong6/6，集中在低容量客户端；B/E/D轨迹一致，不归为认证新增损失。|
|精确性|18缓存、79完成文件、99冻结来源、18 P3方法锚点均通过；530,841,600关系/707,788,800候选检查零错，13报表重生成一致|
|结论边界|8/18严重退化，不支持全部数量档健康；每方法单次，旧seed；跨档表示/类别构成/私有批次数变化，非容量单因素因果|
|代码状态|8个Python文件及协议保持原版本，复用旧训练/认证/协议，不改原源码|

**协议与说明：** [预注册](../../experiments/quantity_heterogeneity/PREREGISTRATION.md) · [README](../../experiments/quantity_heterogeneity/README.md) · [开发验证](../../experiments/quantity_heterogeneity/VALIDATION.md)

**结果与审核：** [正式报告](../../experiments/quantity_heterogeneity/results_full/report.md) · [主审](../../outputs/quantity_heterogeneity_results_20261111/REVIEW.md) · [机器审计](../../outputs/quantity_heterogeneity_results_20261111/audit.json) · [独立复审](../../outputs/quantity_heterogeneity_results_20261111/INDEPENDENT_REVIEW.md)

**归档：** [60份主/内存JSON恢复清单](../../archives/quantity_heterogeneity_raw_20261111.manifest.json) · [完成清单](../../experiments/quantity_heterogeneity/results_full/completed.json)。原环境（含18缓存输入身份）、电源、原报表直接保留；不上传数据/模型/特征。开发smoke不作正式性能证据。


新增证据：[E27 低容量三时点诊断](#e27) · [原报告](../../experiments/low_capacity_diagnostic/results_full/report.md)。

<a id="e27"></a>
## E27 低容量三时点诊断

|项目|记录|
|---|---|
|实验目录|`experiments/low_capacity_diagnostic/`|
|配置与对照|strong/N6/K10，seed1001/1002×IID/α0.1；4×40轮公共LR0.05回放，4×200轮private-only，4×200轮全体LR0.0125|
|验证问题|关闭或减弱公共更新能否解除严重退化，T0/T1/T2观察哪段更新参与集中|
|主要结果|低容量诊断已完成4条40轮基线回放和8条200轮B诊断。基线逐轮匹配旧轨迹；private-only、全体公共LR0.0125均4/4通过160/180/200逐客户端解除严重退化检查。低LR的100张客户端最大簇仍最高97.89%，不等于充分健康聚类，也没有认证省时结论。|
|核验|27完成文件、107来源、4缓存/历史baseline和11报表重生成一致；99旧源不变。基线新增观测仅到40轮，不补造晚期T0/T1/T2。|
|结论边界|仅B、旧seed、有限四配置；公共LR全体变化也改变教师反馈；诊断子集非独立测试集，解除99%阈值不代表充分健康|
|代码状态|7个Python文件保持正式版本，旧源/旧缓存不改|

**说明及协议：** [README](../../experiments/low_capacity_diagnostic/README.md) · [预注册](../../experiments/low_capacity_diagnostic/PREREGISTRATION.md) · [开发验证](../../experiments/low_capacity_diagnostic/VALIDATION.md)

**结果与审核：** [正式报告](../../experiments/low_capacity_diagnostic/results_full/report.md) · [主审](../../outputs/low_capacity_diagnostic_results_20261112/REVIEW.md) · [独立复审](../../outputs/low_capacity_diagnostic_results_20261112/INDEPENDENT_REVIEW.md) · [机器审计](../../outputs/low_capacity_diagnostic_results_20261112/audit.json)

**原始/派生归档：** [无损ZIP及恢复清单](../../archives/low_capacity_diagnostic_20261112.manifest.json)。12份raw JSON按case保存，4份大CSV日志另存derived_logs；解压回原路径后可核验27份完成文件。环境/电源/小表直接保留，数据/表示缓存不上传。


新增证据：[E28 局部公共学习率干预](#e28)。

<a id="e28"></a>
## E28 局部公共学习率干预

|项目|记录|
|---|---|
|实验目录|`experiments/local_public_lr/`|
|配置与对照|strong/IID/seed1001，N6、100/400/700重复、K10、M16384、公共2步；原全体0.05完整200轮回放＋仅client0/3降LR0.0125的200轮B|
|验证问题|只减小低容量客户端公共步幅能否解除晚期严重退化|
|主要结果|strong/IID/seed1001局部公共LR干预完成：仅100张client0/3降至0.0125，其余仍0.05；局部分支160/180/200全部6客户端通过严重退化检查，原0.05持续单簇。局部早期40/60/80轮仍双单簇，属于晚期解除持续退化，不是防止坍缩或充分健康保证。 末轮两小客户端最大簇86.0125%/89.7875%，NMI0.01769/0.05789；历史全局低LR为85.8%/89.575%，仅私有为80.0625%/81.4875%。|
|核验|22完成文件、115来源、原200轮全部非计时字段及10个测试点一致；16报告重生成一致；首轮仅目标client公共更新不同，200轮批次顺序相同|
|边界|单个既有IID配置；未防早期坍缩，公共更新不是唯一触发原因；局部干预仍改变后续教师反馈；不作健康、ACC提升或认证省时保证|
|代码状态|7个Python文件和预注册保持正式版本；旧训练/协议/缓存未改|

**协议与结果：** [README](../../experiments/local_public_lr/README.md) · [预注册](../../experiments/local_public_lr/PREREGISTRATION.md) · [开发验证](../../experiments/local_public_lr/VALIDATION.md) · [正式报告](../../experiments/local_public_lr/results_full/report.md)

**审核：** [主审](../../outputs/local_public_lr_results_20261112/REVIEW.md) · [独立Luna/high复审](../../outputs/local_public_lr_results_20261112/INDEPENDENT_REVIEW.md) · [审计脚本](../../outputs/local_public_lr_results_20261112/audit_results.py) · [机器审计](../../outputs/local_public_lr_results_20261112/audit.json)

**无损归档：** [ZIP与逐文件恢复清单](../../archives/local_public_lr_20261112.manifest.json)。两份原始JSON及超过250KB的派生CSV保存于ZIP，解压回根目录可按completed核验全部22项；缓存/原图/模型不上传。数据身份与公共探针ID仍在环境/原始记录中。


新增证据：[E29 局部LR三配置确认](#e29)。

<a id="e29"></a>
## E29 局部LR三配置确认

|项目|记录|
|---|---|
|实验目录|`experiments/local_public_lr_confirmation/`|
|配置|strong/N6/K10/M16384/公共2步；1001/α0.1、1002/IID、1002/α0.1；仅local_lr B各200轮，无新增baseline|
|主要结果|局部公共LR剩余三配置确认已完成：seed1001/α0.1、seed1002/IID及α0.1各200轮B；160/180/200全部6客户端检查为3/3配置、54/54项通过。此前1001/IID探索单列。早期严重集中仍存在，解除严重退化不等于充分健康聚类；本轮不使用计时或加速结论。|
|末轮100张客户端最大簇|1001/α0.1：88.575%/71.4875%；1002/IID：91.625%/66.0375%；1002/α0.1：90.675%/65.25%|
|核验|22项完成清单、123冻结来源、3份run封印与完整字段、3缓存及旧参照清单通过；13报表重生成一致。54客户端-检查点不是54独立实例。|
|边界|既有seed和数据；只确认新局部规则在3case晚期解除阈值，未防早期退化；局部改变仍影响后续教师反馈；不作ACC提升、充分健康或计算收益主张|
|代码及复审|训练引擎未变；入口执行策略附质量专用修订；本次独立复审补齐最终源码/结果审核，旧开发时未完成记录保留|

**协议及结果：** [README](../../experiments/local_public_lr_confirmation/README.md) · [预注册及执行修订](../../experiments/local_public_lr_confirmation/PREREGISTRATION.md) · [报告](../../experiments/local_public_lr_confirmation/results_full/report.md)

**审核证据：** [主审](../../outputs/local_public_lr_confirmation_results_20261113/REVIEW.md) · [独立Luna/high复审](../../outputs/local_public_lr_confirmation_results_20261113/INDEPENDENT_REVIEW.md) · [审计脚本](../../outputs/local_public_lr_confirmation_results_20261113/audit_results.py) · [机器审计](../../outputs/local_public_lr_confirmation_results_20261113/audit.json)

**归档：** [4个无损ZIP及逐文件恢复清单](../../archives/local_public_lr_confirmation_20261113.manifest.json)。三份原始JSON各自存档，大CSV另存derived_logs；恢复原路径可核验22项清单。日志/环境/小表直接保留，不上传图像、编码器或特征缓存。
