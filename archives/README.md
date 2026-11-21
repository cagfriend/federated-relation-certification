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



2026-11-05新增客户端数固定总量原始结果，3个seed ZIP含54方法与12内存记录，SHA256成员清单见client_scaling_fixed_total_raw_20261105.manifest.json。



2026-11-06新增退化干预与学习率确认归档，7个ZIP保存3条干预、1份历史参照及16份确认封装。封装内5份轨迹复用历史，按origin与source_sha256说明；不能将重复记录计为独立实验。恢复路径与SHA256见lr_recovery_raw_20261106.manifest.json。


## 2026-11-09 P1/P2正式原始记录

[lr_followups_raw_20261109.manifest.json](lr_followups_raw_20261109.manifest.json)列出13个无损ZIP及60个主运行JSON、6个隔离内存JSON的原路径、字节数、SHA256。解压至仓库根目录恢复runs路径后核验各completed.json；内存原记录在专门ZIP内；电源、环境和报表直接保留。数据和表示缓存不在归档内。


## 2026-11-10 P3正式结果

[lr_client_scaling_raw_20261110.manifest.json](lr_client_scaling_raw_20261110.manifest.json)记录11个无损ZIP及54主+12内存JSON的恢复路径/字节/SHA256。解压到仓库根目录后核对completed.json；输入指针、电源、环境和报表原样直接保留。缓存不上传。


## 2026-11-11数量异构原始记录

[quantity_heterogeneity_raw_20261111.manifest.json](quantity_heterogeneity_raw_20261111.manifest.json)列出10个无损ZIP、54主+6内存JSON的路径/大小/SHA256。解压到仓库根目录后校验79完成文件；环境/电源/小报表直接保留，数据/模型/特征不上传。失败配置和负收益均保留。


## 2026-11-12低容量诊断记录

[low_capacity_diagnostic_20261112.manifest.json](low_capacity_diagnostic_20261112.manifest.json)列出5个无损ZIP及全部成员路径/大小/SHA256；12个原始case/branch JSON按case存档，stages/losses_and_deltas/stage_display/stage_events四份大CSV在derived_logs归档。解压到仓库根后核对completed的27文件；环境、电源及小表保留，数据/表示缓存不上传。


## E28局部公共学习率

[local_public_lr_20261112.manifest.json](local_public_lr_20261112.manifest.json)列出ZIP摘要及每个成员的原路径/大小/SHA256；恢复后可核验22项完成清单。旧归档原样保留。


## E29局部LR三配置确认

[local_public_lr_confirmation_20261113.manifest.json](local_public_lr_confirmation_20261113.manifest.json)：三case原始JSON各一ZIP，加大CSV日志ZIP。所有成员保留原路径、大小、SHA256；可恢复22项完成清单。


## E30/E31 无损原始记录

[私有校正恢复清单](private_prior_20261113.manifest.json)含4份主轨迹与大CSV；[计算比较恢复清单](private_prior_compute_20261113.manifest.json)含12主运行及6内存回放。ZIP成员保留完整仓库相对路径、大小与SHA256，可恢复各自completed.json。小报告/环境/完成封印直接保留。



## E32确认原始记录

[恢复清单](private_prior_confirmation_20261114.manifest.json)记录6个case ZIP与54份完整JSON。恢复原路径可核验completed.json的60项。模型、数据和特征缓存不上传。
## E41 精确选路计时归档

[E41 原始记录](e41_routing_raw_records_20261120.zip)含 180 份逐轮结果及各自回执、12 份教师轨迹回执、规则和完成清单。逐轮 JSON 字节与正式运行一致。查看时将该 ZIP 解压至单独目录，教师特征和参数数组由复现入口生成。[审阅](../docs/evidence/EXACT_ROUTING_BOUNDARY_20261120.md) · [来源清单](../docs/evidence/e41_routing/provenance.json)

## E42/E43 原始记录

[E42 新种子重放](e42_confirmation_raw_records_20261120.zip)保存 162 次计时和教师轨迹回执。[E43 完整训练](e43_full_training_raw_records_20261120.zip)保存 18 次审计与 54 次正式计时和配对回执。分别解压到单独目录。教师特征、参数数组和预处理数据由实验入口在本地生成。[复现入口](../docs/REPRODUCIBILITY.md)

## E44/E45 原始记录

[E44 阶段归因](e44_timing_diagnosis_raw_records_20261121.zip)保存 96 次计时。[E45 原始实验](e45_on_demand_raw_records_20261121.zip)保存八条审计与 24 次计时。[E45 补测](e45_on_demand_retest_raw_records_20261121.zip)保存 12 次独立计时和补测回执。分别解压到单独目录，结果与来源摘要见[审阅报告](../docs/evidence/TIMING_DIAGNOSIS_AND_DEMAND_20261121.md)。
