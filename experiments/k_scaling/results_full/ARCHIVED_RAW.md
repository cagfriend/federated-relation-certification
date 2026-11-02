# 原始结果恢复

原始72方法和12内存回放无损分组保存：

- [seed1001：24方法](../../../archives/k_scaling_seed1001_raw_records_20261102.zip)
- [seed1002：24方法+12内存](../../../archives/k_scaling_seed1002_raw_records_20261102.zip)
- [seed1003：24方法](../../../archives/k_scaling_seed1003_raw_records_20261102.zip)

在仓库根目录解压恢复runs/和memory/原路径；[清单](../../../archives/k_scaling_raw_20261102.manifest.json)记录摘要。原93文件完成清单、运行封签及计时未改，本说明为发布新增，不在原清单中；Windows路径跨平台需转换分隔符。没有上传数据、特征、权重或伪标签数组。

[休眠处理版](../../../outputs/k_scaling_sleep_review_20261102/sleep_adjusted/report.md)优先用于解释：只将seed1002/强非IID/K64的共享新增准备成本及两项含准备比值标不可用，头部统计未剔轮。该配置另有6/6单簇，成本数据仍保留，详见[完整审核](../../../outputs/k_scaling_results_20261102/REVIEW.md)。

prepared_metadata/保存24份新K小缓存元数据快照，便于追溯准备成本与资产摘要；完整程序化审核还依赖原冻结环境、旧轨迹及本机缓存，不能声称无依赖重放。
