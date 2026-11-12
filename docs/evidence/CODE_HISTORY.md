# 历史代码与复现状态

盘点基线：[46b25e333228](https://github.com/cagfriend/federated-relation-certification/tree/46b25e333228d0adf3cc418566c63ede11686754)。以下是该提交实际存在的源码清单，不根据旧README命令猜测源码仍在。

## 读取规则

- 当前路径存在源码：只说明可取得该版本；实际运行还可能依赖未上传数据、准备缓存、原机器绝对路径和精确源码摘要。
- 没有Python源码：原报告和清单仍保留；不能称为可一键复现。历史提交是否含完整原驱动需要逐项查证，不凭空补写版本。
- 原始记录ZIP、成员SHA与SOURCE_MANIFEST是证据；不把后来实现冒充原始源码。
- 当前仍使用public_scaling核心的实验依赖该目录，不移动或重构冻结代码。

## E01 overhead_benchmark

- 用途：验证认证与自适应编码各自的收益，定位小更新有利区间。
- 原始入口：[experiments/overhead_benchmark/README.md](../../experiments/overhead_benchmark/README.md)
- 源码状态：0个Python文件。旧驱动缺失，不提供虚假的运行命令。

原驱动的历史取回状态：本次未确认完整原版可恢复。清理说明及现存证据见原复现文档、清单与下面的历史材料索引。

## E02 real_iid

- 用途：自然SGD下的关系一致性、头部净收益和空间代价。
- 原始入口：[experiments/real_iid/README.md](../../experiments/real_iid/README.md)
- 源码状态：0个Python文件。旧驱动缺失，不提供虚假的运行命令。

原驱动的历史取回状态：本次未确认完整原版可恢复。清理说明及现存证据见原复现文档、清单与下面的历史材料索引。

## E03 public_scaling

- 用途：公共规模增大时，生成收益能否转成完整头部收益。
- 原始入口：[experiments/public_scaling/README.md](../../experiments/public_scaling/README.md)
- 源码状态：13个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/public_scaling/__init__.py](../../experiments/public_scaling/__init__.py)|`15959e5760c6e555c62783992db5f569bc197ff1`|
|[experiments/public_scaling/certification.py](../../experiments/public_scaling/certification.py)|`6adfab508e326b22ef99dbf127e1acd3d21f1381`|
|[experiments/public_scaling/codec.py](../../experiments/public_scaling/codec.py)|`67c20e33add5fe929153501633e0c4fdbbfa5b72`|
|[experiments/public_scaling/config.py](../../experiments/public_scaling/config.py)|`7dc69a5d9b86b7822230daed34e2750c8ce9bb1f`|
|[experiments/public_scaling/data.py](../../experiments/public_scaling/data.py)|`0ff9c03594b0bcda2b8d654a1543df4ba693db04`|
|[experiments/public_scaling/engine.py](../../experiments/public_scaling/engine.py)|`9bc9feada372165e22fb36ca3b611b20f186774a`|
|[experiments/public_scaling/graphs.py](../../experiments/public_scaling/graphs.py)|`359cfcc83b7b4073f9976db5900b9a86d8c228eb`|
|[experiments/public_scaling/head.py](../../experiments/public_scaling/head.py)|`ed6e81a24e8efcc7a95933a8157fe0e3edc9edb2`|
|[experiments/public_scaling/protocol.py](../../experiments/public_scaling/protocol.py)|`1fcda45a42d01f4edda09714b51d22cb57f2e3b7`|
|[experiments/public_scaling/report.py](../../experiments/public_scaling/report.py)|`eee294a69ce259fc29c09de219ac4487e3e0049b`|
|[experiments/public_scaling/run.py](../../experiments/public_scaling/run.py)|`944f6b53fea3c098fa3d79ea5ba9b0d8501a1cd5`|
|[experiments/public_scaling/test_scaling.py](../../experiments/public_scaling/test_scaling.py)|`b57a9baf07226678e3bea5d6baf934786f86bd79`|
|[experiments/public_scaling/util.py](../../experiments/public_scaling/util.py)|`8bbe177abe659cd61ec7fed56b3cfb0c024dfc8d`|

## E04 graph_density

- 用途：更密图是否扩大关系认证收益。
- 原始入口：[experiments/graph_density/README.md](../../experiments/graph_density/README.md)
- 源码状态：4个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/graph_density/__init__.py](../../experiments/graph_density/__init__.py)|`665e01a6f02844be9fed341279437cb17f07194c`|
|[experiments/graph_density/analyze.py](../../experiments/graph_density/analyze.py)|`b4b61b4a177809d704047e888c5f304a1bb46998`|
|[experiments/graph_density/run.py](../../experiments/graph_density/run.py)|`d3dbeec28266e9f22d5f5964ba469193c3a89a82`|
|[experiments/graph_density/test_orchestration.py](../../experiments/graph_density/test_orchestration.py)|`42b77e293a45555416070d750cb1e32c229eba92`|

## E05 cost_diagnostics

- 用途：省掉的教师计算是否被认证维护抵消。
- 原始入口：[experiments/cost_diagnostics/README.md](../../experiments/cost_diagnostics/README.md)
- 源码状态：4个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/cost_diagnostics/__init__.py](../../experiments/cost_diagnostics/__init__.py)|`344969048c91b9f9dcaf912500871e411a1c5679`|
|[experiments/cost_diagnostics/profiler.py](../../experiments/cost_diagnostics/profiler.py)|`a5cdd88f514d839acc0c239e5d4c8845880e219a`|
|[experiments/cost_diagnostics/run.py](../../experiments/cost_diagnostics/run.py)|`2872b3db0c5b9b46c303850e4153fbca44decf5b`|
|[experiments/cost_diagnostics/test_diagnostics.py](../../experiments/cost_diagnostics/test_diagnostics.py)|`a29c60ec5f714df25a7b731a78b6f1e7bfc70f14`|

## E06 path_selection

- 用途：动态规则能否优于静态E/D选择。
- 原始入口：[experiments/path_selection/README.md](../../experiments/path_selection/README.md)
- 源码状态：4个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/path_selection/__init__.py](../../experiments/path_selection/__init__.py)|`fb409372e6c956f77ec375fdc3326d1da601d4d8`|
|[experiments/path_selection/run.py](../../experiments/path_selection/run.py)|`d2c8795a4bcfeb9f8ba6ff1c128d8d3f05f1ebcb`|
|[experiments/path_selection/selection.py](../../experiments/path_selection/selection.py)|`b02fbcb67596264d8bf9e20278512023619c80ed`|
|[experiments/path_selection/test_selection.py](../../experiments/path_selection/test_selection.py)|`9d989cb29e9afaeb9fe5303b9139d3af2c61fd26`|

## E07 aggregator_recovery

- 用途：提交状态能否正确交接，复制是否节省累计通信。
- 原始入口：[experiments/aggregator_recovery/README.md](../../experiments/aggregator_recovery/README.md)
- 源码状态：4个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/aggregator_recovery/__init__.py](../../experiments/aggregator_recovery/__init__.py)|`2dbcefd380b5aaa8592510cc2679153c25d53674`|
|[experiments/aggregator_recovery/protocol.py](../../experiments/aggregator_recovery/protocol.py)|`ba1730e2b6b485cf49d98537b438eb4a05a7db95`|
|[experiments/aggregator_recovery/run.py](../../experiments/aggregator_recovery/run.py)|`afbbeea905157781bbe18662a9d4d64041439ac8`|
|[experiments/aggregator_recovery/test_recovery.py](../../experiments/aggregator_recovery/test_recovery.py)|`af043ad7b4377e7fbd61216802d20c6214756a7b`|

## E08 noniid_clustering

- 用途：非IID下精确保持、净收益及质量事件。
- 原始入口：[experiments/noniid_clustering/README.md](../../experiments/noniid_clustering/README.md)
- 源码状态：6个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/noniid_clustering/__init__.py](../../experiments/noniid_clustering/__init__.py)|`7dbceef0601d3ced6b2c07e659c3892a79af84d2`|
|[experiments/noniid_clustering/data.py](../../experiments/noniid_clustering/data.py)|`554b67aca3d1b4e890606017eb2b137b4b5e5f5d`|
|[experiments/noniid_clustering/engine.py](../../experiments/noniid_clustering/engine.py)|`62f3a458f92c7a035e75430bcc96857387f266e8`|
|[experiments/noniid_clustering/report.py](../../experiments/noniid_clustering/report.py)|`b7d5cc7075b65de66bacbc585889157fb7c4a4fb`|
|[experiments/noniid_clustering/run.py](../../experiments/noniid_clustering/run.py)|`9548048f3a19fea4303f9aee7a814abc22c037a6`|
|[experiments/noniid_clustering/test_noniid.py](../../experiments/noniid_clustering/test_noniid.py)|`e5fd010453aa831a3acc6e02839abf7ed309dc79`|

## E09 collaboration_mechanism

- 用途：区别公共更新、额外计算与正确跨客户端信息的作用。
- 原始入口：[experiments/collaboration_mechanism/README.md](../../experiments/collaboration_mechanism/README.md)
- 源码状态：7个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/collaboration_mechanism/__init__.py](../../experiments/collaboration_mechanism/__init__.py)|`816dabcb95d5f388cafc8e5cc2640e10c70769a4`|
|[experiments/collaboration_mechanism/diagnostics.py](../../experiments/collaboration_mechanism/diagnostics.py)|`bca7f66b5b4928a32c809ef19aa268beaf10f2cc`|
|[experiments/collaboration_mechanism/engine.py](../../experiments/collaboration_mechanism/engine.py)|`6fe109bf014f1a09fc90f3c24c2c0d1bb9705aef`|
|[experiments/collaboration_mechanism/report.py](../../experiments/collaboration_mechanism/report.py)|`fa53f6f18b35291c6a59e6f30231dc76858dd537`|
|[experiments/collaboration_mechanism/run.py](../../experiments/collaboration_mechanism/run.py)|`f8447cc4bf068b8d0b35b68e3e71077c45b0ff9b`|
|[experiments/collaboration_mechanism/targets.py](../../experiments/collaboration_mechanism/targets.py)|`c5159f954db1450a879a986b95a1593b282b50d2`|
|[experiments/collaboration_mechanism/test_mechanism.py](../../experiments/collaboration_mechanism/test_mechanism.py)|`658bef698d6f835ba0cef38be728f7dda957d3e3`|

## E10 public_budget

- 用途：隔离原先公共库增大同时增加学生训练预算的混杂。
- 原始入口：[experiments/public_budget/README.md](../../experiments/public_budget/README.md)
- 源码状态：7个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/public_budget/__init__.py](../../experiments/public_budget/__init__.py)|`0974855a7fea7b9737079540a0e3c37bf82588a0`|
|[experiments/public_budget/design.py](../../experiments/public_budget/design.py)|`df8b94a0831bd329192381f3c71a87cea6a2d59d`|
|[experiments/public_budget/engine.py](../../experiments/public_budget/engine.py)|`7f714b66352f2157950c2a8733ff38c8b4a223d3`|
|[experiments/public_budget/report.py](../../experiments/public_budget/report.py)|`8c3dabaa8e1f3ccc61edd80ebf08c37b49c52052`|
|[experiments/public_budget/run.py](../../experiments/public_budget/run.py)|`be3c3cbd3a4fa75cd96f28ee75e6c18ed1ef05b7`|
|[experiments/public_budget/student.py](../../experiments/public_budget/student.py)|`b8ffff41edb9680ff973e7596c6256eb42863b90`|
|[experiments/public_budget/test_budget.py](../../experiments/public_budget/test_budget.py)|`3bd93977d90aea9703466eee36b7c972fc946d70`|

## E11 private_workload

- 用途：私有训练占比下降时认证的完整头部收益。
- 原始入口：[experiments/private_workload/README.md](../../experiments/private_workload/README.md)
- 源码状态：8个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/private_workload/__init__.py](../../experiments/private_workload/__init__.py)|`7683c2d41fdafc43542630b7d6d4ee1a623e5a8d`|
|[experiments/private_workload/design.py](../../experiments/private_workload/design.py)|`496d6eda5a11fbb40691dea915e365bbf868307c`|
|[experiments/private_workload/engine.py](../../experiments/private_workload/engine.py)|`c307f5b82678af54a5e4d6e9644bfd8d63ce913e`|
|[experiments/private_workload/report.py](../../experiments/private_workload/report.py)|`6cdc929c54910e5953d312eb0f7e0c8db3fffd0b`|
|[experiments/private_workload/run.py](../../experiments/private_workload/run.py)|`1854ffe5fc17201664c015b59f5c930226638c45`|
|[experiments/private_workload/sampling.py](../../experiments/private_workload/sampling.py)|`1261339b1acd14714c52f5ad3c48581af19c3a5b`|
|[experiments/private_workload/student.py](../../experiments/private_workload/student.py)|`1dcee9c8912a5261a907c733d8edb008e8a542fa`|
|[experiments/private_workload/test_workload.py](../../experiments/private_workload/test_workload.py)|`07294da51fa92d9c9ba996eb9d20bce2b58a33cf`|

## E12 perf_confirmation

- 用途：微小D/E收益能否在独立进程复现，并披露运行噪声。
- 原始入口：[experiments/perf_confirmation/README.md](../../experiments/perf_confirmation/README.md)
- 源码状态：6个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/perf_confirmation/__init__.py](../../experiments/perf_confirmation/__init__.py)|`b6a1ae029d8ad8d4c535c3524ce5f0e1c0ca60cb`|
|[experiments/perf_confirmation/design.py](../../experiments/perf_confirmation/design.py)|`ec1062f46be4bced1902bbf602ee5b7d88cc3867`|
|[experiments/perf_confirmation/engine.py](../../experiments/perf_confirmation/engine.py)|`857ede47b1f7ff763b116ce9a3ac71e5c9e2efe0`|
|[experiments/perf_confirmation/report.py](../../experiments/perf_confirmation/report.py)|`f5ca39688d916ecd442d90ec053664bb912a00d8`|
|[experiments/perf_confirmation/run.py](../../experiments/perf_confirmation/run.py)|`418678867c07f5128bbb085cea10f343cd7bff3e`|
|[experiments/perf_confirmation/test_confirmation.py](../../experiments/perf_confirmation/test_confirmation.py)|`7443cd5dc5b65a76f3a81d950db65bc883cc1571`|

## E13 stl10_transfer

- 用途：自然彩色图像与不同公共数据源下的计算迁移。
- 原始入口：[experiments/stl10_transfer/README.md](../../experiments/stl10_transfer/README.md)
- 源码状态：8个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/stl10_transfer/__init__.py](../../experiments/stl10_transfer/__init__.py)|`fae938c9d8d66fb6ed541b672d91aa15c9e94ab3`|
|[experiments/stl10_transfer/data.py](../../experiments/stl10_transfer/data.py)|`100b080ea0e6f8dae945219f16b151e9dac21292`|
|[experiments/stl10_transfer/design.py](../../experiments/stl10_transfer/design.py)|`5094a4270bc5b27619d70f2120c6adc644dbd7ef`|
|[experiments/stl10_transfer/engine.py](../../experiments/stl10_transfer/engine.py)|`da147d950ec900f0f764c0de2a7b65bea0d09a39`|
|[experiments/stl10_transfer/report.py](../../experiments/stl10_transfer/report.py)|`c43f140f361aa1e6ae0f9261e208e89fcbdad5a5`|
|[experiments/stl10_transfer/run.py](../../experiments/stl10_transfer/run.py)|`c27ecdd4ae731e1d798940b14efbddf41336a501`|
|[experiments/stl10_transfer/test_data.py](../../experiments/stl10_transfer/test_data.py)|`0bdf1efd0f37ba90b32054788e8959162351631e`|
|[experiments/stl10_transfer/test_run.py](../../experiments/stl10_transfer/test_run.py)|`bf0df3700f333dc691179db3b046e0865591cff4`|

## E14 stl10_diagnostics

- 用途：定位私有训练、公共更新与动态反馈的影响。
- 原始入口：[experiments/stl10_diagnostics/README.md](../../experiments/stl10_diagnostics/README.md)
- 源码状态：5个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/stl10_diagnostics/__init__.py](../../experiments/stl10_diagnostics/__init__.py)|`ee0d17e94a679b68044a9726c1147a996e95f9cf`|
|[experiments/stl10_diagnostics/probes.py](../../experiments/stl10_diagnostics/probes.py)|`5a109edd166339640313988d78bcaecab49194ff`|
|[experiments/stl10_diagnostics/run.py](../../experiments/stl10_diagnostics/run.py)|`37b731ab5bb47429ff277c62f0266ad71c27639d`|
|[experiments/stl10_diagnostics/test_probes.py](../../experiments/stl10_diagnostics/test_probes.py)|`19475ec386500a17b91f7652fbb14d9d0d505692`|
|[experiments/stl10_diagnostics/test_run.py](../../experiments/stl10_diagnostics/test_run.py)|`cb18dc56f0b3984432236742d4b0039a992ac40b`|

## E15 stl10_public_steps

- 用途：只减少公共更新预算能否缓解退化。
- 原始入口：[experiments/stl10_public_steps/README.md](../../experiments/stl10_public_steps/README.md)
- 源码状态：3个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/stl10_public_steps/__init__.py](../../experiments/stl10_public_steps/__init__.py)|`8055fb1e51fde56c3a962cdf93d4684adbb08860`|
|[experiments/stl10_public_steps/run.py](../../experiments/stl10_public_steps/run.py)|`f19dc9208e405b6c44cda55cca72cc3c4ecd72a3`|
|[experiments/stl10_public_steps/test_run.py](../../experiments/stl10_public_steps/test_run.py)|`de98908f4b394e8e5b99071360dc92c91cadac35`|

## E16 stl10_longrun

- 用途：低公共预算在长程和新seed/非IID下是否仍通过退化护栏。
- 原始入口：[experiments/stl10_longrun/README.md](../../experiments/stl10_longrun/README.md)
- 源码状态：6个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/stl10_longrun/__init__.py](../../experiments/stl10_longrun/__init__.py)|`ca69824eabfc0653deb9fc8fb5d2ec962c6628eb`|
|[experiments/stl10_longrun/design.py](../../experiments/stl10_longrun/design.py)|`83fa875038541609eb58ece27a5206bdd35cff6a`|
|[experiments/stl10_longrun/engine.py](../../experiments/stl10_longrun/engine.py)|`3b98e4dfd664f7fa6a7b00873fa2acd09f6fab9c`|
|[experiments/stl10_longrun/report.py](../../experiments/stl10_longrun/report.py)|`2d3a8371109bb6970ca2298d7f28ff7c201aa08d`|
|[experiments/stl10_longrun/run.py](../../experiments/stl10_longrun/run.py)|`5ae42528b1cf2c35a2baa3c1892b9e17c151bc83`|
|[experiments/stl10_longrun/test_design.py](../../experiments/stl10_longrun/test_design.py)|`512e324215911330958dfcb0e47feb8bf2ef9ae9`|

## E17 stl10_compute

- 用途：在固定健康公共预算下重新比较认证成本。
- 原始入口：[experiments/stl10_compute/README.md](../../experiments/stl10_compute/README.md)
- 源码状态：5个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/stl10_compute/__init__.py](../../experiments/stl10_compute/__init__.py)|`afcffbac1ae80468c769ba1f4e224ede21624fa7`|
|[experiments/stl10_compute/design.py](../../experiments/stl10_compute/design.py)|`8f97538356e075e2331a6af540fca155c5ae522e`|
|[experiments/stl10_compute/report.py](../../experiments/stl10_compute/report.py)|`f00958f238d24531f04b20f325e0c68b7dbb47cb`|
|[experiments/stl10_compute/run.py](../../experiments/stl10_compute/run.py)|`3d72894f0cb43675d896f0f836519612d313b61d`|
|[experiments/stl10_compute/test_run.py](../../experiments/stl10_compute/test_run.py)|`307fb09ff53b1600e9d80036cd92b48f20befd75`|

## E18 stl10_repeat_confirmation

- 用途：已有配置下方向与判定是否复现。
- 原始入口：[experiments/stl10_repeat_confirmation/README.md](../../experiments/stl10_repeat_confirmation/README.md)
- 源码状态：5个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/stl10_repeat_confirmation/__init__.py](../../experiments/stl10_repeat_confirmation/__init__.py)|`639153d14dc347df3270b0876c0a22210010b61d`|
|[experiments/stl10_repeat_confirmation/design.py](../../experiments/stl10_repeat_confirmation/design.py)|`aa6594047a5fa2d99fe5789da138b941d6fc92e2`|
|[experiments/stl10_repeat_confirmation/report.py](../../experiments/stl10_repeat_confirmation/report.py)|`6c45034d14097e796b1207b021f5e86238d2d616`|
|[experiments/stl10_repeat_confirmation/run.py](../../experiments/stl10_repeat_confirmation/run.py)|`036f811421850184a1a535b01610f9a768d34581`|
|[experiments/stl10_repeat_confirmation/test_run.py](../../experiments/stl10_repeat_confirmation/test_run.py)|`65ae0089ba40129c391299484ac43dab8332d936`|

## E19 k_scaling

- 用途：K增长时认证维护与空间成本是否抵消省算。
- 原始入口：[experiments/k_scaling/README.md](../../experiments/k_scaling/README.md)
- 源码状态：7个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/k_scaling/__init__.py](../../experiments/k_scaling/__init__.py)|`f8b1defc305434c285ac03f3d0d51d049aab3ab7`|
|[experiments/k_scaling/data.py](../../experiments/k_scaling/data.py)|`69f130a3e079e1cc6491de6eddc101cc7f8d204b`|
|[experiments/k_scaling/design.py](../../experiments/k_scaling/design.py)|`f0baba76a1fedc4b84e7e4b47362178406080ed0`|
|[experiments/k_scaling/engine.py](../../experiments/k_scaling/engine.py)|`8d857f6d0cebd2251d7c79576dade6defeb37cd5`|
|[experiments/k_scaling/report.py](../../experiments/k_scaling/report.py)|`b44abaceae1ebb14edb75b52ea45414039b01d1d`|
|[experiments/k_scaling/run.py](../../experiments/k_scaling/run.py)|`7111a2734a4e7bdcfe283752cab0d9b0055c7cbc`|
|[experiments/k_scaling/test_run.py](../../experiments/k_scaling/test_run.py)|`53d899b8347378085b5734de58774a8a559a2612`|

## E20 client_scaling

- 用途：客户端增长时计算、通信、内存和退化边界。
- 原始入口：[experiments/client_scaling/README.md](../../experiments/client_scaling/README.md)
- 源码状态：8个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/client_scaling/__init__.py](../../experiments/client_scaling/__init__.py)|`86687a9bbd73d73b2eb2a2d33d65700f5b9c5df2`|
|[experiments/client_scaling/data.py](../../experiments/client_scaling/data.py)|`a791a18b7be99ee184f88e309ea3ae1db3af437e`|
|[experiments/client_scaling/design.py](../../experiments/client_scaling/design.py)|`f1227725196bd95f61a0eb8eadcce9350f84117a`|
|[experiments/client_scaling/engine.py](../../experiments/client_scaling/engine.py)|`4107fd1720daa8d9e1b98a11dcf37997c5780a8d`|
|[experiments/client_scaling/report.py](../../experiments/client_scaling/report.py)|`a2884a3cb588df3c123fb2e5780223b18aef69fa`|
|[experiments/client_scaling/run.py](../../experiments/client_scaling/run.py)|`9318e18981e05094e683971441c5375e88e27fb9`|
|[experiments/client_scaling/telemetry.py](../../experiments/client_scaling/telemetry.py)|`8ef009cb1b55e84149b6f28f81b9d46c11288bf0`|
|[experiments/client_scaling/test_run.py](../../experiments/client_scaling/test_run.py)|`fb645dfa35b3d6102aa99c4916280ff11f531f99`|

## E21 collapse_intervention

- 用途：公共更新过强是否参与维持和放大退化。
- 原始入口：[experiments/collapse_intervention/README.md](../../experiments/collapse_intervention/README.md)
- 源码状态：5个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/collapse_intervention/__init__.py](../../experiments/collapse_intervention/__init__.py)|`876e407b9b7ab3927e8c72190c9ad3ca44def62d`|
|[experiments/collapse_intervention/engine.py](../../experiments/collapse_intervention/engine.py)|`3e2e1d1fc043b80faba4044898bd8d0956d581a7`|
|[experiments/collapse_intervention/report.py](../../experiments/collapse_intervention/report.py)|`8f8335b6a4df10ea770c5ad22ce86215505fe16f`|
|[experiments/collapse_intervention/run.py](../../experiments/collapse_intervention/run.py)|`f249229519928fa9afa071443f7b043d3d9282b9`|
|[experiments/collapse_intervention/test_run.py](../../experiments/collapse_intervention/test_run.py)|`fac049a31626a46aa119a59f6c24c8291e8a017c`|

## E22 public_lr_confirmation

- 用途：不改公共边数与步数，仅减更新强度是否可恢复并维持健康配置。
- 原始入口：[experiments/public_lr_confirmation/README.md](../../experiments/public_lr_confirmation/README.md)
- 源码状态：6个Python文件。实际逐文件清单如下。

|文件|基线Git blob SHA|
|---|---|
|[experiments/public_lr_confirmation/__init__.py](../../experiments/public_lr_confirmation/__init__.py)|`cabab4d3da634daefaf77814cb6bde918db66fc1`|
|[experiments/public_lr_confirmation/data.py](../../experiments/public_lr_confirmation/data.py)|`98d942837eb07e76a9c749f67996eec2fdd1d5ae`|
|[experiments/public_lr_confirmation/design.py](../../experiments/public_lr_confirmation/design.py)|`a7fb35929017a09223c3ad869517d30b0c980ceb`|
|[experiments/public_lr_confirmation/report.py](../../experiments/public_lr_confirmation/report.py)|`3c66252ba1b9a8cee3570d0e99568b7ffeec292e`|
|[experiments/public_lr_confirmation/run.py](../../experiments/public_lr_confirmation/run.py)|`494850d7d58f088c96d38acb5888f2a9d7c7e300`|
|[experiments/public_lr_confirmation/test_run.py](../../experiments/public_lr_confirmation/test_run.py)|`09a63593f8ea7914f1a29fb4bd5981f9c585d178`|

## 后续本地包

P1/P2代码尚未出现在本次远端基线，不能通过远端相对源码链接假装已可下载。状态与本地证据快照见[LOCAL_FOLLOWUPS.md](LOCAL_FOLLOWUPS.md)。

## 原有材料的完整文件清单

所有基线文件与Git blob SHA见[BASELINE_FILES.json](../history/BASELINE_FILES.json)。它覆盖实验内未逐条展开的CSV、JSON、图片、封印、审计和归档成员清单。

较早的清理和迁移说明原文仍在[复现边界](../REPRODUCIBILITY.md)；不要把其中旧运行命令当作当前可用性保证。


## E23/E24 后续发布增补，2026-11-09

原基线清单保持原样；新增两个包各5个Python文件，未改既有104份P1依赖源码。原缓存与锚点仍是运行前提。

|源码|SHA256|
|---|---|
|[__init__.py](../../experiments/lr_compute/__init__.py)|`996c2958d45507b57aee8f3f32d4c461048c7fff3f54ea21768b5ea4250c7b1d`|
|[design.py](../../experiments/lr_compute/design.py)|`1a12becdffd0f992240b43335901f211a00d082b1b683695ccb03440ab4d70bd`|
|[report.py](../../experiments/lr_compute/report.py)|`d496bda9f37eff39aaa6768bafe7596ea663be07ba6deeb3ab57558d99b18f6f`|
|[run.py](../../experiments/lr_compute/run.py)|`10ae5efddd17690587833c2c0cc0d1d1dd181cf880d3ce49ac4ae7955e2ba4e7`|
|[test_run.py](../../experiments/lr_compute/test_run.py)|`2d570aef7ea32783b3af02b7d2a44ed760384d9b9548420996b2e896a41bab1c`|
|[__init__.py](../../experiments/lr_repeat/__init__.py)|`dd7f13e2e8919fcaf8edb5c49857ed1ffb239e10b608720da6a3009ff7bf6fba`|
|[design.py](../../experiments/lr_repeat/design.py)|`e38d57d49548640b07df4a14ef80ddfcf080e7931203923d7fccce887a1a2dd6`|
|[report.py](../../experiments/lr_repeat/report.py)|`57e3cfbf51570cbaa54cc244bb244056b442f04c30137be82bcb3a2727c9f7a3`|
|[run.py](../../experiments/lr_repeat/run.py)|`a82700e86eb6d2fc599488e13378fc49f995ce3c622567808ce8c1c04ec5fd40`|
|[test_run.py](../../experiments/lr_repeat/test_run.py)|`53962f30341d135af47c9dfc2ccdcc5ed64c0336b9be17ac1756c5d7e7a26386`|


## E25 P3固定每客户端规模，2026-11-10发布

5个Python文件直接复用旧冻结核心，仅新计划设public_weight=0.5；源文件SHA256如下。旧依赖不改，仍需原缓存/数据准备和精确版本。

|源码|SHA256|
|---|---|
|[__init__.py](../../experiments/lr_client_scaling/__init__.py)|`99f527e0d1c739f891d8f74a71afcf867e675d2c36848aeb6bfc52c91d714638`|
|[design.py](../../experiments/lr_client_scaling/design.py)|`3f1e4974cc456261fd1bb4ea3fafa24208f5af982d59c8c5090d9e9ed292e8d7`|
|[report.py](../../experiments/lr_client_scaling/report.py)|`105cf0d5f2e9aa9bdeaac52eeda308bdbffe9d3d5863c3eb41b1e4a9b288647e`|
|[run.py](../../experiments/lr_client_scaling/run.py)|`3255a126a6fb413e050d0ae1c47a661e2d54f6e0ce333bf113ad7782849fddd8`|
|[test_run.py](../../experiments/lr_client_scaling/test_run.py)|`d9e4b1c32eb891832752417fff9245da55b709deb1240834940948a125feb9f3`|


## E26数量异构，2026-11-11增补

8个Python文件，保持正式运行版本；旧训练/认证核心与P3来源不改。非均量划分与准备器独立，equal强制使用旧P3缓存及方法锚点。

|源码|SHA256|
|---|---|
|[__init__.py](../../experiments/quantity_heterogeneity/__init__.py)|`80d4d8febace56a8649b517d7b82513552bcd626b2f2dc938075a9c370765cd2`|
|[data.py](../../experiments/quantity_heterogeneity/data.py)|`70444736529196c60d1630f4592a23ebdb3ba047e6a72a5549c93699ca1b125f`|
|[design.py](../../experiments/quantity_heterogeneity/design.py)|`c9c4d3e38f5ec4fb8edc02de0e654b84c3273cdf069a56769d8b8868f41d8f88`|
|[engine.py](../../experiments/quantity_heterogeneity/engine.py)|`cbf4e8edeb628b28fe38ccdfb461c4f0a2c37663a0e4c1a413a81b76a4d69a01`|
|[partition.py](../../experiments/quantity_heterogeneity/partition.py)|`987a13ac3364f377974d689c04fb87d0d976a5b59de9f4f574035d737528db69`|
|[report.py](../../experiments/quantity_heterogeneity/report.py)|`42b86947b06e1f1b95635bc8b5dd51717cac84c428416a5b5fdc8284365c6c0a`|
|[run.py](../../experiments/quantity_heterogeneity/run.py)|`a41fa74838de0f270f6155588c54fa71e182f423adda33e7602b37d30f5a5eb0`|
|[test_run.py](../../experiments/quantity_heterogeneity/test_run.py)|`6b83150ba7842726daedb1bf8f1269f97dca348c22659ad165c44966d37bd91f`|


## E27低容量诊断，2026-11-12增补

7个Python文件原版，公共/私有训练核心与旧99来源不改；本包增加三时点只读观测和private-only跳过公共更新。SHA256如下。

|源码|SHA256|
|---|---|
|[__init__.py](../../experiments/low_capacity_diagnostic/__init__.py)|`a8721997cab3e739c9425937efd348ceadb42f3256317dae7450c0925ac64e5d`|
|[design.py](../../experiments/low_capacity_diagnostic/design.py)|`7b01c66a6c377fa5dce1155618f08a213bcb8a0f7d1ddfea178fd64cc848da73`|
|[engine.py](../../experiments/low_capacity_diagnostic/engine.py)|`d5bb298967b1cc28e753b9af58ac4e9597be806056261cebf5ee31e4a55f5e79`|
|[probes.py](../../experiments/low_capacity_diagnostic/probes.py)|`82a987c9985d258e2c4e5c68c966e0225e5e4235105df6730b28ca348bdc6486`|
|[report.py](../../experiments/low_capacity_diagnostic/report.py)|`e8780a05111f5af0b09000dfaabf420820f0f9b55f73f9cf84fe6c5c3c7a0206`|
|[run.py](../../experiments/low_capacity_diagnostic/run.py)|`12e9e011b39fe2b434fa99d20ddde8ba0eae567e5e715472f306d01459e59280`|
|[test_run.py](../../experiments/low_capacity_diagnostic/test_run.py)|`78093f707b4be8e4631de24961c1f966febf91db8c04fee42bbaa46ef6e9fc22`|


## E28局部学习率，2026-11-12

只在公共学生更新调用时传入逐客户端Spec；旧源不改。

|源码|SHA256|
|---|---|
|[__init__.py](../../experiments/local_public_lr/__init__.py)|`4dd1be3d96d20d8010f9bff02b5901501d336a3cc1c5af4bb2a4ca05b547c4b5`|
|[design.py](../../experiments/local_public_lr/design.py)|`f7d06413fc564b69335288c2331af1052f3a4023a2b9af9249d9479bd761154c`|
|[engine.py](../../experiments/local_public_lr/engine.py)|`8e0a1fb48d5447b7396253d7cbbd18e1187cff0c742912f55ac4a07697b216b3`|
|[probes.py](../../experiments/local_public_lr/probes.py)|`8cf9b3e133973f364325e8f94ddf55b65903f19f4b717187f20a255201f94b7c`|
|[report.py](../../experiments/local_public_lr/report.py)|`08791442583826840d2c249b4bafdb0c8a30ecb19fd4036b9b5c0b1d75fbc818`|
|[run.py](../../experiments/local_public_lr/run.py)|`27870c94511751632e57efd5581265189f37f06484eb519664e1e7f18ca849db`|
|[test_local_public_lr.py](../../experiments/local_public_lr/test_local_public_lr.py)|`c8be85d22c6d16cc6a0f1b838d609ec6762144104d2f88011e0808162b8f5ff2`|


## 局部LR剩余三配置确认，2026-11-12：代码就绪

直接复用E28训练引擎；新增三case调度/身份核验/报表。正式实验尚未启动。

|源码|SHA256|
|---|---|
|[__init__.py](../../experiments/local_public_lr_confirmation/__init__.py)|`d1503d317aef769d4bbc90c73ee56ba6384bc6c794e965ffbbcb9ad9721c55f6`|
|[design.py](../../experiments/local_public_lr_confirmation/design.py)|`09b25ee4a3262067367de571cdc2a5e44544400ee3de7a7dd899ab4c4c3800ae`|
|[engine.py](../../experiments/local_public_lr_confirmation/engine.py)|`4e87031cba514e9dfb241b01a87813dcd25886de26ab648808817e1d4b4be15b`|
|[probes.py](../../experiments/local_public_lr_confirmation/probes.py)|`d767bd3f0eca9eb5717d492cfcfabafc5ef3533d22b8761a3ae633488b55feda`|
|[report.py](../../experiments/local_public_lr_confirmation/report.py)|`1a5ac12a36ad1d987e51dedd6cce16659056dc7be1e574db2b3d6f06b9ced63b`|
|[run.py](../../experiments/local_public_lr_confirmation/run.py)|`0120c03b38480987e2b5487797537f1182b05598e3c8b08fbaa453986bff98aa`|
|[test_confirmation.py](../../experiments/local_public_lr_confirmation/test_confirmation.py)|`f07acfdc0b98dea05d8716af0b62acf21d4d8dbf7589f550af21c03c86f6b990`|
