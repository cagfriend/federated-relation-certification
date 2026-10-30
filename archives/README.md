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
