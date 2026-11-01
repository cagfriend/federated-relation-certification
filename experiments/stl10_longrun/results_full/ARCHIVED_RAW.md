# 原始轨迹无损归档

8 条正式 B 轨迹保存在 [stl10_longrun_raw_20261101.zip](../../../archives/stl10_longrun_raw_20261101.zip)。在仓库根目录解压即可恢复 experiments/stl10_longrun/results_full/runs/ 下原文件。

原 completed.json / finished.json 及全部 run_sha256 保持不变。completed.json 使用 Windows 相对路径分隔符，跨平台核对时须转换路径；清单描述的是解压后的原结果集合，本说明是发布时新增文件，不属于原清单。未上传数据集、特征缓存、模型或预训练权重。

主审阅在 [REVIEW.md](../../../outputs/stl10_longrun_results_20261101/REVIEW.md)。复核脚本从仓库根目录执行 python -m outputs.stl10_longrun_results_20261101.audit；除解压原始记录外，复核运行环境和缓存锚点还需要原本地冻结环境及既有 STL-10 迁移结果/缓存，不能把此脚本描述为无外部依赖的纯结果审计。
