# IID / non-IID＋模型宽度异构：真实聚类实验

本轮回答两个问题：数据类别分布不同时，关系认证是否保持相同训练结果并节省资源；完整协作相对Local是否有聚类质量收益。学习目标、关系图和认证不作新调整，不预设协作一定有效。

## 固定方案

|项目|完整配置|
|---|---|
|数据|官方Fashion-MNIST，训练60000、统一测试10000|
|划分|IID、Dirichlet α=0.5、Dirichlet α=0.1|
|公共池|每seed预留16384，三个划分使用完全相同的public IDs；实际关系/训练使用前4096|
|私有集合|剩余43616张，各划分覆盖同一私有全集；每客户端数量为7270/7270/7269/7269/7269/7269|
|客户端|6个，MLP宽度512×3、2048×3，10个聚类输出|
|准备|每划分/seed独立用本客户端私有无标签图像训练去噪AE5个epoch，然后提取固定特征、做一次本地KMeans|
|头部训练|冻结编码器，私有固定伪标签CE＋公共共簇关系BCE，200轮；图度1，其他优化器/批次沿用核心配置|
|种子|404、505、606，用于本次场景探索；不是新的留出复核|
|方法|Local、B全量生成、E逐样本认证、D关系认证|

3划分×3seed=9组，每组4条真实训练轨迹，总36条。每组只准备一次，四个方法共享私有数据、特征、伪标签、初始头和随机训练顺序。IID也在本批次重跑，避免拿私有样本量不同的历史Local作对照。

## 类别偏斜如何控制

每客户端先抽取十类的Dirichlet偏好，再用IPF将期望分配拟合到**精确客户端容量和私有类别总量**，最后通过整数残差运输分配样本。因此这是固定容量约束的Dirichlet划分，不是无约束、客户端数量也随之变化的常见实现。

客户端数量差最多1张，先隔离类别偏斜。实际类直方图、熵、缺失类别、分配矩阵和ID摘要记录在各准备目录的 `partition.json`；不能只凭α宣称实际异构程度。随机种子间不保证α变小后所有客户端的每个统计都严格单调，也不按结果重抽划分。

新增官方训练标签只用于划分与诊断，测试标签用于评估。AE、KMeans、SGD继续调用原核心实现，adapter仅向准备函数注入图像ID，不向训练器提供训练真标签。所有方法的私有目标仍来自KMeans。训练标签官方MD5在代码中校验；来源为 [Fashion-MNIST官方README](https://github.com/zalandoresearch/fashion-mnist/blob/master/README.md)。

划分专用缓存路径包含partition名称、data.py源码摘要以及原准备配置/seed摘要。不会用IID编码器缓存充当non-IID编码器；准备步骤中断且没有完成wrapper标记时会停止，需保留问题目录后选择新的cache路径。不会静默认可半完成缓存。

## 运行

已在当前环境确认CUDA可用。工作区根目录执行：

```powershell
cd C:\Users\tjp\Documents\Codex\2026-10-14\new-chat
D:\anaconda\python.exe -m experiments.noniid_clustering.run --preset full --prepare-device cuda --download --memory-audit
```

`--download`只下载缺失的官方IDX文件并校验全部文件。AE准备使用指定设备，头部训练及认证始终CPU float64、单BLAS线程。需要仅CPU时改为 `--prepare-device cpu`。

`--memory-audit`在36条配对训练之外，**再执行36次单方法独立进程回放**，用于测量峰值工作集，计时不作速度比较。各回放最终参数摘要、持久数组占用必须与配对训练一致。若只先跑质量/耗时/通信与持久数组，可以省略该选项；不能把同进程同时存在四个方法时的进程峰值冒充某个方法的峰值。

中断后恢复：

```powershell
D:\anaconda\python.exe -m experiments.noniid_clustering.run --preset full --resume
```

默认输出 `experiments/noniid_clustering/results_full`，默认新缓存位于同包 `prepared/`。可以用 `--output`、`--cache`、`--data-dir` 指定独立目录。恢复沿用已保存preset、设备、memory开关与计划；源代码、环境变化拒绝恢复，已完成case保留，未完成case从第1轮重跑。不能在恢复时悄悄新增memory开关。

小配置与测试：

```powershell
D:\anaconda\python.exe -m unittest experiments.noniid_clustering.test_noniid -v
D:\anaconda\python.exe -m experiments.noniid_clustering.run --preset smoke --memory-audit
```

smoke仍是真实官方数据，但缩小为训练1024、公共池128/实际32、测试128、两客户端宽度32/64、AE1epoch、头3轮。覆盖3划分×3seed×4方法及可选36次内存回放；仅验证执行路径，不能用于正式性能或学习质量结论。

## 如何看结果

- `completed.json`：全部9组完成标志及产物哈希；额外内存回放数量单列。
- `report.md` / `summary.json` / `summary.csv`：D/B、D/E关系生成/头部训练/共享准备加头部时间，最终B-Local质量差；均先逐seed配对再汇总。
- `final_clients.csv`：每客户端NMI/ARI/ACC、簇占用和最大簇比例；最差客户端指标同时报告，完整时间曲线在case.metrics中，每20轮及最终评估。
- case JSON：全部逐轮头摘要、通信字节、认证统计、验证次数、准备耗时、最终指标和划分审计。
- `memory_summary.csv`：启用隔离回放后生成，含进程峰值工作集和最终摘要；CPU进程峰值不等于GPU显存，也未测encoder准备阶段峰值。

B/E/D每轮头摘要和消息字节一致，关系/候选赢家/聚合接收计数逐轮与全量oracle核对，已记录评估要求一致。不把Local强制与它们保持同一训练轨迹：Local本来就没有公共训练。

质量看B相对Local是否有跨seed稳定收益；若没有，保留负结果。性能看D相对B/E是否保留净收益，特别是关系生成在头部总训练中占比及额外内存。候选命中率高不自动意味着整体更快。跨客户端簇编号不需对齐，但相同K并不保证客户端学到相同语义。

## 成本口径与边界

头部时间包括方法初始化、私有SGD、教师快照/认证、序列化交换、公共SGD；oracle、摘要和评估排除。准备成本C0包含每划分独立AE、完整最大公共池/私有/测试特征、KMeans及写文件，不按4方法摊薄。原始case同时保存C0和公共特征阶段时间。

`shared_preparation_plus_head_seconds`给所有方法计入本组共享C0。Local不需要公共特征准备，因此这不是Local最低独立成本，不能据该列宣称协作方法相对Local加速。D/B/E共享C0的配对比较没有此不对称。若要严格比较到同一质量的Local独立总成本，另做对应准备/停止条件实验。

持久数组字节排除共享特征/图、Python对象和瞬时临时数组；可选隔离进程峰值反映载入特征后的单方法头训练范围，包含进程基础内存。不能混同两种指标。

当前仍是冻结编码器、固定leader0、成员全在线、可靠内存消息，没有接入恢复协议。非IID学习验证不证明真实网络容错；旧恢复实验也不证明本轮训练集成。浮点guard仍是实用数值保护，不是形式化IEEE证书。

本轮没有新调参、按测试集选最好轮次、重抽最有利划分或新增动态选路。使用统一最终轮次评价，保留全部已测划分与种子。
