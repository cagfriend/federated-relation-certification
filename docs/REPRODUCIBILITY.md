# 代码、运行与历史结果边界

原始逐轮大JSON以无损ZIP保存，解压即可恢复原路径；汇总与代码直接可读。见[归档与恢复说明](../archives/README.md)。

## 当前可运行代码

当前自包含入口为 `experiments.public_scaling.run`，不导入已删除的旧驱动程序。四个核心模块从旧已验证代码原样迁移；迁移和旧代码清理证据见 [清理记录](../outputs/experiment_cleanup_20261029/completed.json)。

原始正式运行环境：Anaconda Python3.12.7、NumPy1.26.4/MKL2023.1、SciPy1.13.1、scikit-learn1.5.1、PyTorch2.7.1+cu118。GPU仅用于编码器准备；头训练与认证在CPU float64、单BLAS线程执行。复现性能需要相应硬件与软件环境，普通依赖安装不保证得到相同计时。

在克隆后的仓库根目录运行：

```powershell
python -m pip install -r experiments/public_scaling/requirements.txt
python -m unittest experiments.public_scaling.test_scaling -v
python -m experiments.public_scaling.run --preset smoke --suite all --download --memory-audit --output runs/smoke
```

当前有13项测试，包含梯度数值检查、公共梯度重复端点、候选认证及真实SGD轨迹一致、固定私有划分、嵌套图、准备缓存、文件损坏拒绝和结果目录保护。部分测试使用明确标注的开发fixture，不可作为真实数据性能结果。

## 从头跑公共库规模实验

```powershell
python -m experiments.public_scaling.run --preset full --suite public --download --prepare-device cuda --memory-audit --output runs/public
```

没有CUDA可改成 `--prepare-device cpu`。默认数据目录为 `experiments/real_iid/data`，默认准备缓存为 `experiments/public_scaling/prepared`。这些目录未提交；首次会重新准备编码器、固定特征和私有伪标签。不要把输出指定为已有正式结果目录。

同一seed对最大公共候选池与相同私有集只准备一次。M=4096/8192/16384共用这一准备，因此私有集43,616固定，不把小M未使用的公共候选样本重新分配进私有集。

主性能口径是含初始化的完整头部训练流程T。`with_shared_preparation_seconds` 为最大池共同准备C0+该配置加载+T，不能解释成每个M最低独立准备成本，也不能把C0按方法/配置数均摊。oracle、评估和内存回放的计时排除在方法性能之外。

## 后续图密度实验

在同一机器、未改变源码和准备缓存时，可复用已有公共库规模结果中的M4096/degree1：

```powershell
python -m experiments.public_scaling.run --preset full --suite graph --prepare-device cuda --memory-audit --reuse-from experiments/public_scaling/results_public --output runs/graph
```

**上述复用命令不能保证在新克隆机器直接成功。** 原始结果固定记录了原机器的准备绝对路径与哈希，而准备缓存未上传；复用会严格拒绝缺失/不匹配环境、源码、路径或缓存。新机器应去掉 `--reuse-from`，加 `--download`，完整重跑三档图密度；或先在同一新机器运行 `runs/public`，再指定该新结果作为复用来源。

## 结果与证据索引

- [初始全量/自适应编码对照](../experiments/overhead_benchmark/results_all/)。
- [更新幅度探索](../experiments/overhead_benchmark/results_sweep/)与[边界加密](../experiments/overhead_benchmark/results_sweep_refine/)。
- [原环境独立种子复核](../experiments/overhead_benchmark/results_sweep_holdout_original_env/)。同目录另保留不同运行环境的 `results_sweep_holdout`，以环境记录区分，不能混合挑选最好结果。
- [真实IID训练](../experiments/real_iid/results_full/)及[审阅](../experiments/real_iid/analysis_20261029/RESULTS_REVIEW.md)。
- [公共库规模正式结果](../experiments/public_scaling/results_public/)及[审阅](../outputs/public_scaling_results_20261030/RESULTS_REVIEW.md)。
- `results_smoke`、`validation_smoke_*`和`validation_reuse_*`只作程序路径验证，不构成正式性能结论。

原始JSON保持字节不变，所以环境、prepared路径和历史源码清单可能包含原机器绝对路径。这些路径是历史证据，不是新机器可直接访问的文件。已上传缓存清单但没有上传缓存本身。

## 历史脚本删除与可复现范围

2026-10-29用户明确要求删除已完成的旧实验代码，仅保留结果。旧 `experiments/overhead_benchmark` 和 `experiments/real_iid` 的Python驱动已删除；旧结果、文档和清单保留，部分清单所指向的旧源码已不存在。旧README中的旧模块命令因此不再可运行。

当前仓库没有暗中恢复这些脚本。它保存当前可运行的规模实验代码和原样迁入的四个核心模块，不能声称所有历史实验均能用完整原始驱动一键重现。历史字节保留与迁移证据见 [DELIVERY_MANIFEST.json](../DELIVERY_MANIFEST.json)及[清理记录](../outputs/experiment_cleanup_20261029/)。

桌面TXT已转换为UTF-8存入 [历史方法笔记](history/user_method_notes_20261029.txt)，其中包含早期设想与尚未实现的内容。当前规范以 [METHOD.md](METHOD.md)及代码为准，不能把历史笔记里的预期功能当成已完成实验。

## 核验保存结果

每个正式case有载荷摘要，`completed.json`记录结果JSON和源码摘要。最新主审另核验了25个结果JSON、132个准备资产和13个源码文件，并逐轮核对全部九组B/E/D轨迹，见 [audit.json](../outputs/public_scaling_results_20261030/audit.json)。

仓库不包含132个准备资产；因此引用原机器缓存的完整审计程序在新克隆后会因资产缺失而不能直接执行。可以先核验仓库内已有文件，再在原环境或自行生成的新实验上做完整缓存核验。重新生成的编码器/缓存不保证与历史GPU数值结果逐字节相同。

## 图密度正式结果与新入口

图密度实验现已完成。`experiments.graph_density.run`仅封装原训练核心，默认复用原机器公共库结果，源码/依赖/准备缓存必须匹配。新克隆机器不能直接复用未上传的缓存；应按上文去掉复用的核心命令完整重跑，或者先在新机器产生自己的public结果。

新增诊断入口：

```powershell
python -m experiments.graph_density.analyze --output experiments/graph_density/results_graph
```

它检查原始结果与当前核心版本/环境，不会重跑训练，但原机器准备目录记录仍限制跨机核验；离线可直接读取CSV、JSON和审阅报告。新包包含3项测试与缩小真实数据路径验证记录；正式结果检查见[审计](../outputs/graph_density_results_20261030/audit.json)。

## 成本诊断入口与限制

```powershell
python -m experiments.cost_diagnostics.run --check-only
python -m experiments.cost_diagnostics.run
python -m experiments.cost_diagnostics.run --resume
```

默认来源为原机器的 `experiments/graph_density/results_graph`，依赖未上传的准备缓存、相同源码与环境；新克隆机器不能直接恢复这些原机器路径。需要先在新机器生成自己的完整三seed graph参考结果，再用 `--reference` 指向它。可直接读取汇总与审阅；无损解压归档后可核对原始文件摘要，但这不等于重做训练。

诊断独立冻结四个新增源码文件，保持原训练核心13个源码不变。两项针对性测试及缩小路径/恢复验证记录随包保存。计时边界、运行命令和输出见 [成本诊断README](../experiments/cost_diagnostics/README.md)。原始计时记录保留字节不变，不用插桩墙钟宣布完整训练加速。


## 连续缓存路径选择入口

```powershell
python -m unittest experiments.path_selection.test_selection -v
python -m experiments.path_selection.run --preset full --check-only
python -m experiments.path_selection.run --preset full
python -m experiments.path_selection.run --preset full --resume
```

正式结果已完成。默认参考 `experiments/graph_density/results_graph`，在原环境重跑E一次并核对历史摘要；不是从旧JSON还原教师权重。原机器准备缓存不上传，新机器需要先生成自己的完整三seed graph参考与有效准备资产，再用 `--reference` 指向它。原始大JSON解压恢复后可以核对文件哈希，但不能重建未保存的完整权重或缓存数组。

性能口径详见[新实验README](../experiments/path_selection/README.md)。`VALIDATION.json`和包内`INDEPENDENT_REVIEW.md`记录运行前的小规模检查；本轮正式结果审阅位于[结果审阅](../outputs/path_selection_results_20261030/RESULTS_REVIEW.md)，二者不要混作同一轮性能证据。所有正式记录字节保持不变，九组原始case已无损归档。

按用户要求清理的是原工作区已完成旧实验的本地执行源码，结果与共同依赖保留。GitHub既有代码和历史均保留，供复现旧实验；本次新增源码使用独立package，公共核心13个源码哈希不变。


## 聚合者交接与恢复协议

```powershell
python -m unittest experiments.aggregator_recovery.test_recovery -v
python -m experiments.aggregator_recovery.run --preset full
python -m experiments.aggregator_recovery.run --preset full --resume
```

该包不依赖Fashion-MNIST或旧准备缓存，输入由seed生成合法共簇关系。保持实验及公共核心源码、Python/NumPy版本才可恢复原记录。完整配置包含18组/54条协议回放，非训练实验；运行前smoke证据在包内VALIDATION.json，正式结果另见 outputs/aggregator_recovery_results_20261030/RESULTS_REVIEW.md。

原始18个case已无损归档，解压后可以用同seed重建输入核对保存目标与通信分类账，但结果摘要不能还原完整消息执行历史。ACK、可靠原子提交/复制屏障和未覆盖故障边界详见实验README。GitHub既有代码继续保留供复现；清除旧实验源码只发生在原工作区，未删除历史记录。


## 非IID＋模型宽度异构（已正式完成）

在仓库根目录使用项目同一Python环境（原环境D:\anaconda\python.exe）：

```powershell
python -m unittest experiments.noniid_clustering.test_noniid -v
python -m experiments.noniid_clustering.run --preset full --prepare-device cuda --download --memory-audit
```

可用CPU准备，但必须用新输出目录、不能假称复用了原CUDA准备身份。正式主实验9组/36条训练；memory-audit额外执行36条单方法完整轨迹，只取CPU工作集峰值，丢弃其耗时。原正式结果目录已完成；复跑请指定新的 --output 目录，原机器续跑使用同路径 --resume。保存身份检查源码、运行库与本机缓存绝对路径，异机复现需重新准备与新输出，不是拿现有摘要直接 --resume。

原始case无损ZIP保留路径和字节；小结果/内存回放/完整清单直接可读。outputs/noniid_results_20261030/preparation只保存9组prepared.json/partition.json清单，含特征资产摘要和实际类别直方图，不含原始数据、特征数组或编码器。正式审计脚本需要原缓存/官方IDX才能完全重跑；下载新数据和重训不能保证跨硬件字节级相同。completed.json校验解压后的结果，不把ZIP替换后的GitHub目录当成原本已展开布局。

包内VALIDATION.json与INDEPENDENT_REVIEW.md为实验前smoke/代码证据，formal_training_started=false是其生成时状态；正式完成与审核以results_full/completed.json、outputs/noniid_results_20261030/audit.json和RESULTS_REVIEW.md为准。冻结原实验源码和证据，不改写历史准备记录。


## 跨客户端关系知识机制消融（正式完成）

```powershell
python -m unittest experiments.collaboration_mechanism.test_mechanism -v
python -m experiments.collaboration_mechanism.run --preset full --prepare-device cuda --download --output runs/mechanism_full
```

9组36条训练；原配置复用noniid_clustering准备缓存，首次无缓存则重新私有AE/KMeans准备。完整数据/编码器/特征缓存未上传。默认历史参考位于noniid_clustering/results_full，原始JSON已归档时需先解压全部历史case；本机绝对路径不能异机直接 --resume。原结果目录已完成，复跑采用新输出；原机恢复使用 --resume 并保持源码/运行库/缓存/参考身份。

原始9case保存5400条位打包输入关系和7128条梯度探针，可从日志重建目标，但未保存全历轮模型参数；重新前向仍需要重跑训练。summary.json、diagnostics.csv、target_diagnostics.csv三份较大派生文件也无损归档在collaboration_mechanism_derived_logs.zip。按ARCHIVE_MANIFEST.json解压到原路径后，可校验completed.json的全部26份原始文件摘要。小报表、完成清单、环境和准备指针直接可读。

包内VALIDATION.json和INDEPENDENT_REVIEW.md是实验前开发/smoke证据，formal_mechanism_training_started=false为历史生成时状态；正式结果以results_full/completed.json及outputs/mechanism_results_20261031审核为准。audit_results.py的完整验证依赖原缓存与历史参考case，不能仅凭小汇总重建教师前向。计时列仅作诊断，不是新的D/E测速或用户实际等待总时长。
