# 原始逐轮记录归档

18条原始记录按seed无损保存，每个ZIP包含该seed的两划分×三方法共6条轨迹：

- [seed1001](../../../archives/stl10_compute_seed1001_raw_records_20261101.zip)
- [seed1002](../../../archives/stl10_compute_seed1002_raw_records_20261101.zip)
- [seed1003](../../../archives/stl10_compute_seed1003_raw_records_20261101.zip)

在仓库根目录解压即可恢复experiments/stl10_compute/results_full/runs/。归档清单见[manifest](../../../archives/stl10_compute_raw_20261101.manifest.json)，发布前逐文件验证解压字节一致。

原completed.json、finished.json、run_sha256和计时均保持不变。原清单使用Windows相对路径分隔符，跨平台核验时转换路径。本说明为发布新增，不在原27文件清单中。未上传数据、特征缓存或模型。

冻结环境和结果来源见environment.json。实际执行代码为本次同步上传的run.py/test_run.py修复版，修复说明见[运行前审核](../../../outputs/stl10_compute_review_20261101/REVIEW.md)。[结果审核](../../../outputs/stl10_compute_results_20261101/REVIEW.md)的完整重核需要旧迁移/长程原始记录和原机器缓存，不能把它视为无依赖的结果读取工具。
