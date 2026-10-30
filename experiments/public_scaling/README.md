# 公共样本库与图规模实验

当前可运行入口为 `experiments.public_scaling.run`。原来已完成实验的运行代码按用户要求清理，旧结果、环境、审计记录和准备数据继续保留。新实验自包含，认证、编解码、提交协议和头训练计算沿用已验证核心，不依赖已清理模块。

## 先验证路径，再运行正式实验

在 PowerShell 中使用原来的 Anaconda 环境：

```powershell
Set-Location -LiteralPath 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
& 'D:\anaconda\python.exe' -m experiments.public_scaling.run --preset smoke --suite all --memory-audit --output experiments/public_scaling/results_smoke
```

smoke 使用真实 Fashion-MNIST 的1024张训练图像，公共池128，公共规模32/64/128，另外检查32个样本的度4/8图；两客户端宽度32/64、3轮、一个种子404。只用于路径验证，不能作正式性能结论。已存在的官方数据复用；缺少数据时增加 `--download`。

正式第一阶段：

```powershell
& 'D:\anaconda\python.exe' -m experiments.public_scaling.run --preset full --suite public --prepare-device cuda --memory-audit --output experiments/public_scaling/results_public
```

这是3个公共规模 × 3方法 × 3种子，共27次配对方法训练。`--memory-audit` 默认只对最大M条件的B/E/D额外运行9次隔离内存回放；这些回放时间不混入性能计时。若需每个配置的完整隔离峰值，可用 `--memory-scope all`，会增加到27次回放。关闭内存测量时去掉 `--memory-audit`，各组仍记录持久状态字节。

GPU仅用于私有编码器预训练与固定特征准备；正式头训练、教师生成和认证都在CPU float64、单线程BLAS上执行。没有CUDA时将 `--prepare-device cuda` 改为 `cpu`，但不同准备设备属于不同准备缓存。

## 冻结配置与公平性

| 项目 | full 配置 |
|---|---|
| 数据 | Fashion-MNIST，训练60000、测试10000 |
| 先固定的公共候选池 | 16384，固定随机顺序 |
| 先固定的私有数据 | 43616，客户端大小7270/7270/7269/7269/7269/7269 |
| 公共规模 | 4096、8192、16384，前缀嵌套 |
| 图 | 度1，2048/4096/8192条无向边，较小图旧配对保留 |
| 客户端 | 同家族MLP，512宽3个、2048宽3个 |
| K | 10 |
| 种子 | 404、505、606，配置顺序按已记录种子预先打乱 |
| 编码器 | 各客户端仅私有无标签AE预训练5 epoch，随后冻结 |
| 私有目标 | 一次K-means得到固定伪标签，CE训练头 |
| 每轮 | 私有CE 1 epoch → 固定教师快照 → 关系/精确计数聚合 → 公共关系BCE 1 epoch |
| 优化器 | 线性头float64普通SGD，lr=0.1；私有batch128、边batch256 |
| 预算 | 200轮，公共权重1；每20轮和最终轮评价 |
| 方法 | B全量、E逐样本认证、D关系认证；同一自适应全量/差分编码 |

每种子只预训练/准备一次，所有M和图度复用相同私有图像、编码器、伪标签、私有/测试特征及头初态。较小M下未使用的公共候选池图像不进入私有数据。训练不读取真实训练标签。

全量B先对每个公共样本计算一次教师输出，再判断边关系，不为每条边重复教师前向。E/D的未确定部分真实重算；仅真实计算端点可刷新候选缓存。下一轮参数变化包含前一轮公共更新加本轮私有更新。每个学生在收到当前精确计数目标后，用当前头重新前向并反向；不复用教师缓存充当学生前向，不跳过完整公共图的训练。

每配置内部B/E/D从相同头和相同批次顺序出发，逐轮轮换方法执行顺序；完整oracle核对硬关系、解码、计数和接收目标，并核对公共更新后头参数摘要和消息轨迹。任何不一致即停止，不修补后继续。不同M/图度的学习轨迹允许不同，不作跨配置参数相等要求。

原真实IID实验私有数据是55904张，不能直接作为新4096组的公平基线；本入口会运行新的4096基线。Local未加入每配置重复对照，本阶段主要验证相对B的执行开销和学习过程保持。

## 后续图密度实验，保留第一阶段结果

公共规模阶段结束后，用同样源码和准备设备启动新目录：

```powershell
& 'D:\anaconda\python.exe' -m experiments.public_scaling.run --preset full --suite all --prepare-device cuda --reuse-from experiments/public_scaling/results_public --memory-audit --output experiments/public_scaling/results_all
```

`--reuse-from` 只接受此新实验入口生成、源码/环境/种子/逐配置参数/准备路径完全匹配且已完成的结果。逐文件核对后复制相同的原始case结果到新目录，记录来源与SHA256，不修改来源。三档公共规模不重复训练，只新增M4096、度4和8两组的18次训练；合计45次。`--suite graph` 则仅选择4096的度1/4/8三组。

度1图是度4图的子图，度4图又是度8图的子图；均无自环、无重边，每点度精确。M4096下边数2048/8192/16384，每客户端每轮公共SGD次数8/32/64。代码不通过改大batch或减少epoch抵消这些真实工作量。

`largest`内存口径在all中覆盖最大M与最大度两组，3方法×3种子×2配置=18次回放；不会自动导入先前内存回放。若此次只需训练配对结果，可去掉 `--memory-audit`。

## 中断后继续

```powershell
& 'D:\anaconda\python.exe' -m experiments.public_scaling.run --output experiments/public_scaling/results_public --resume
```

恢复采用结果目录记录的确切计划、种子、设备、路径与内存选项，忽略其他覆盖参数。源码和Python/依赖环境必须相同。完整case逐文件保留；中断的当前case从第1轮重跑，不支持轮内恢复。损坏或截断文件会拒绝覆盖，检查后应选新目录。未完成的准备目录也拒绝自动复用。

## 结果与成本口径

- `environment.json`：冻结计划、执行顺序、源码和环境。
- `m4096_d1_seed_404.json`等：完整逐轮记录、逐客户端指标、头摘要、检查计数、图SHA与共享私有准备证据；带payload校验值。
- `summary.csv`：逐case/seed/方法耗时、指标、端点和优化步数、持久状态。
- `paired_summary.json`：严格按配置和同seed配对D/B、D/E，记录比值、绝对省时、中位数、范围、胜出数和raw pairs。
- `memory_*.json`、`memory.json`、`memory_summary.csv`：性能计时外的隔离进程回放；含输入与评价，不含GPU预训练。
- `report.md`：汇总；按实际预定seed判断完成与partial，smoke有明确说明。
- `completed.json`：全部完成标志、运行数量和结果JSON哈希。只有存在此文件并且检查通过才算计划完成。

主要比较包含初始化的头训练T与教师关系生成时间；同时看私有/公共/消息阶段、实际端点、SGD步数、缓存与通信。新增认证不宣称压缩与B/E相同的通信流量。

C0一次准备整个最大公共池及相同私有数据，包含测试特征和磁盘写入。C0+加载+T是共用最大池准备策略的成本核算，小M也承担全池C0，不是各M各自最低独立准备成本；不按方法或配置数均摊，实际复用缓存不再次支付C0。下载、oracle检查、指标评价与输出单独于T，不把它们加入方法加速比。

这是六客户端串行模拟、固定临时聚合者和内存应用层消息，没有实际网络、选举、故障恢复或能耗测量。公共样本和图增大不保证提高相对省时、聚类质量或认证通过比例。

## 开发验证

```powershell
& 'D:\anaconda\python.exe' -m unittest experiments.public_scaling.test_scaling -v
```

测试包含梯度数值检查、固定私有分区、公共前缀与嵌套图、稀疏/密图的B/E/D实际SGD轨迹与oracle、前一轮公共更新计入下一轮认证、准备缓存复用、损坏和非空输出保护。测试中生成的特征/IDX明确为development fixture，不能用作真实实验结论。
