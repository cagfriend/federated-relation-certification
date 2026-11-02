# K增长的计算与内存边界

在STL-10既有冻结表示上改变输出簇数10/16/32/64；仅重做新K的私有KMeans，不重训编码器，不修改旧实验及缓存。真类数仍是10，实验是输出维度与过聚类训练的开销敏感性。

正式72次方法运行，可另启12次K10/64隔离内存回放。K10的新B核对已有两步B轨迹，全部方法重新计时。较大K可能增加KMeans和认证成本；不预先承诺省时。

PowerShell先进入工作区根目录：

```powershell
cd "C:\Users\tjp\Documents\Codex\2026-10-14\new-chat"
D:\anaconda\python.exe -m experiments.k_scaling.run --preset full --memory-audit
```

中断后同一目录续跑（沿用环境中冻结的内存回放选择）：

```powershell
D:\anaconda\python.exe -m experiments.k_scaling.run --preset full --resume
```

无需重新下载数据；复用stl10_transfer/results_full的6个准备标记，以及stl10_compute/results_full中6个K10的B锚点。新小缓存位于本包prepared_k/，结果位于results_full/。开始先做KMeans，可能暂时没有Running方法行；有Preparing提示。准备阶段进程中断留下非空未完成小缓存时会报错并指出路径，应检查后用新--cache目录重新准备，避免误用部分结果；完整小缓存会复用。

若中断发生在准备阶段、尚未写出environment.json，不能使用--resume；按上述小缓存处理后重新执行首次运行指令。

单元与smoke：

```powershell
D:\anaconda\python.exe -m unittest experiments.k_scaling.test_run
D:\anaconda\python.exe -m experiments.k_scaling.run --preset smoke --memory-audit
```

输出runs.csv、paired_cost.csv、paired_summary.csv、memory.csv、summary.json、report.md和原始逐轮JSON。计时进程的峰值包含oracle；隔离memory.csv只覆盖端点K和一个seed，切勿混用。完整边界及口径见PREREGISTRATION.md。
