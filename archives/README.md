# 原始逐轮记录归档

仓库直接保留代码、说明、汇总、内存档案和审阅记录。体积超过200 KB的实验JSON逐轮记录以无损ZIP保存；全部原始字节未修改，摘要见 `ARCHIVE_MANIFEST.json`。

在仓库根目录解压恢复原来的目录结构：

```python
from pathlib import Path
from zipfile import ZipFile
for archive in Path("archives").glob("*_raw_records*.zip"):
    with ZipFile(archive) as z:
        z.extractall(".")
```

请只解压本仓库已核验的归档。解压后原始结果目录及其 `completed.json` 文件清单即可对应；数据/模型/特征准备缓存仍未上传，原机器缓存绝对路径不能在新机器直接使用。


## STL-10公共2步计算对照（2026-11-01）

新增stl10_compute_seed1001/1002/1003_raw_records_20261101.zip，共18条完整原始记录；各ZIP在仓库根目录解压恢复原路径。字节摘要和成员见[清单](stl10_compute_raw_20261101.manifest.json)。原completed/finished/run封签未改。[结果与恢复说明](../experiments/stl10_compute/results_full/ARCHIVED_RAW.md)。


## STL-10重复计时（2026-11-02）

stl10_repeat_seed1001/1002/1003_raw_records_20261102.zip各18条，共54条。根目录解压恢复原路径；原封签未改。[归档清单](stl10_repeat_raw_20261102.manifest.json) · [恢复与结果说明](../experiments/stl10_repeat_confirmation/results_full/ARCHIVED_RAW.md)。


## K输出簇数实验（2026-11-02）

k_scaling_seed1001/1002/1003_raw_records_20261102.zip共72方法+12内存，根目录解压恢复；seed1002归档含全部内存回放。成员及摘要见[k_scaling清单](k_scaling_raw_20261102.manifest.json)。原结果封签不改，休眠处理版另存，详见[恢复与结果说明](../experiments/k_scaling/results_full/ARCHIVED_RAW.md)。
