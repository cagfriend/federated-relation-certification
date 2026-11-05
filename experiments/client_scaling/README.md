# 客户端数量扩展实验

重点：N=2/6/12 时 D 相对 B/E 的计算收益是否保留，以及聚合、通信和内存的增长。固定总量和固定每客户端量分开运行。详细冻结配置见 [PREREGISTRATION.md](PREREGISTRATION.md)。

先插电，关闭自动休眠；在工作区根目录运行：

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.client_scaling.run --preset full --regime fixed_total --prepare-device cuda --memory-audit
```

默认读取本地已有官方 STL-10，无需重新下载。总私有5000张，N2/6/12，54次方法运行加12次隔离内存回放；结果在 `experiments/client_scaling/results_full_fixed_total/`。N6复用旧缓存；N2/N12首次需要分别准备独立客户端模型与特征，因此准备阶段比上一轮K实验长。进度先显示 Preparing，之后显示 Running；等最终 Finished。

中断后使用同一分支和输出路径：

```powershell
D:\anaconda\python.exe -m experiments.client_scaling.run --preset full --regime fixed_total --resume
```

恢复使用已冻结的设备、内存选项和路径。已经完整结束时只验证保存文件摘要，不重跑。若准备缓存尚未完成，错误会指出目录；保留/移出该未完成目录后再恢复。不要修改已有结果或原实验代码。

第一分支完成并审核后，独立运行固定每客户端400张：

```powershell
D:\anaconda\python.exe -m experiments.client_scaling.run --preset full --regime fixed_per_client --prepare-device cuda --memory-audit
```

这也是54+12次，总样本800/2400/4800，另存 `results_full_fixed_per_client/`。可用 `--cache 'D:\client_scaling_cache'` 将新缓存放到空间较大的盘；运行前指定，恢复后固定。两分支全量新缓存可能占数十GB；每个客户端公共/测试特征独立存储。`--regime all` 可一次运行两个分支，但报告分开统计，不推荐初次就扩大运行量。

输出包括 `report.md`、配对耗时、逐客户端质量、退化事件、可选隔离峰值、原始运行JSON、输入缓存标记、冻结环境、全程采样电源日志、完成文件清单。原始计时不自动删异常。主指标是完整头部与生成耗时，准确率不要求提高；严重坍缩会明确标记。

开发验证（不会运行正式实验）：

```powershell
D:\anaconda\python.exe -m unittest experiments.client_scaling.test_run
D:\anaconda\python.exe -m experiments.client_scaling.run --preset smoke --regime all --memory-audit
```

复用现有训练引擎，固定表示、K10、每客户端公共2步。串行总时间及均摊客户端时间都不是多机并行轮时延；通信是已有协议的序列化字节统计，不是实测带宽。
