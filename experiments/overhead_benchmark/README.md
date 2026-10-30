# 硬共簇关系：受控开销实验

本代码实现已约定的四组实验，不启用 research-rigor 或其他 skill。它只回放固定特征上的合成线性头参数更新，测量**关系生成＋应用层消息编解码、聚合和提交**的成本；不是聚类训练，不计算 NMI，不声称验证数据异构、学习价值、真实网络时延、选举、故障恢复或端到端 FL 加速。原 TXT 未修改。

已完成独立复审及默认配置运行，见[验收与结果记录](VALIDATION.md)和[独立复审报告](INDEPENDENT_REVIEW.md)。

## 更新幅度扫描（2026-10-28）

本轮六档扫描和三档边界补点已完成，见[完整结果与验收](SWEEP_RESULTS_20261028.md)、[合并汇总](results_sweep_analysis/combined_summary.csv)和[新增独立复审](SWEEP_INDEPENDENT_REVIEW.md)。旧结果保持原样。

在原程序上新增 `--suite sweep`，默认六档 `0.02 / 0.05 / 0.08 / 0.2 / 0.5 / 2.0`，每档三个种子、每种子 200 轮，其他配置仍为 6 客户端、4096 公共样本、K=8、固定匹配图及 512/2048 两类宽度。比较以下三组，共 **54 次方法运行**：

| 组 | 关系生成 | 消息编码 |
|---|---|---|
| B | 全量前向 | 自适应全量／差分 |
| E | 逐样本预测认证；非 singleton 样本真实重算 | 与 B 完全相同 |
| D | 关系认证；只对未决边的未确定端点去重重算 | 与 B 完全相同 |

三组独立缓存，共用该档、该种子的固定特征、图、参数快照及消息协议。E 使用相同变化界，但不承担关系专用的候选 bitset 构造、集合交集检查；它先确认每个样本的当前标签，再生成边关系。三组的实际通信轨迹必须完全一致，程序自动检查这一点。**扫描识别的是认证的计算收益区间，不是 D 相对 B/E 的新增通信收益。**

从工作区根目录运行：

```powershell
Set-Location -LiteralPath 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
python -m experiments.overhead_benchmark.run --suite sweep --output experiments/overhead_benchmark/results_sweep
```

扫描默认不额外进行 54 个内存回放。需要时仍可加 `--memory-audit`；其代价、隔离进程和计时排除方式与原程序相同。先验证小规模完整流程可用：

```powershell
python -m experiments.overhead_benchmark.run --suite sweep --scales 0.02 0.2 --samples 64 --dimensions 8 16 --rounds 3 --seeds 101 --memory-audit --output experiments/overhead_benchmark/results_sweep_smoke
```

边界附近补点时显式设置新幅度，必须使用新的输出目录：

```powershell
python -m experiments.overhead_benchmark.run --suite sweep --scales 0.10 0.12 0.16 --output experiments/overhead_benchmark/results_sweep_refine
```

每个种子的幅度执行顺序由独立调度 RNG 重排，避免固定从小到大；这不改变特征／参数更新 RNG。每档重新初始化，不能把上一档训练状态或认证缓存带到下一档。不同幅度使用相同初态及标准正态扰动序列，仅缩放更新量。

扫描输出：

- `sweep_scale_0p02_seed_101.json` 等：18 个配对配置的逐轮数据；文件名包含可无损往返的幅度值，避免覆盖。
- `summary.csv`：54 行方法汇总，新增加 `scale` 列；逐配置完成后更新，异常中断前已经完成的配置仍有结果。
- `sweep_summary.csv` 和 `sweep_summary.json`：每幅度一行，给出三个方法的耗时和重算比例、**同种子配对后的 D/B 与 D/E 成本比中位数及最小／最大值**、D 胜出的种子数和两种关系变化率。不是“各方法耗时中位数再相除”。
- `source_hashes.json` 和 `environment.json`：本次源码摘要、环境和完整运行计划。

小于 1 的 D/reference 成本比表示该配置观测到节省；还应检查三个种子是否一致及包含初始化的生成／整体阶段成本。结果不被强制解释成单调、精确的更新阈值；不跨未测区间插值。`scale` 仍是合成扰动控制量，不是训练学习率。关系变化率与计数变化率在计时之外采集，编码器自身必须进行的差分比较仍计入测量时间。当前阶段不使用旧运行的耗时拼接新对照。

**旧结果保护**：现在所有入口均拒绝写入非空结果目录。之前 `results_all`、`results_verified`、`results_smoke` 的文件保持原样；要重跑请指定新的目录。原 `--suite main / boundary / all` 仍保持原来的方法组合，`all` 不自动包含本次扫描。

## 四个方法组和默认配置

| 组 | 关系生成 | 消息编码 |
|---|---|---|
| A | 全量真实前向 | 全量 |
| B | 全量真实前向 | 每条消息选择全量／稀疏差分／无变化确认 |
| C | 候选集合关系认证＋未决端点去重重算 | 全量 |
| D | 同 C，各自独立缓存 | 同 B，各自独立通信状态 |

- 6 个客户端；前 3 个固定特征维度 512，后 3 个为 2048；同为线性聚类头，K=8。
- 公共样本 ID 为 0..4095；各客户端拥有自己的固定特征，均为 float64 合成高斯矩阵。
- 固定随机匹配图：4096 个样本、2048 条不重复边，每个样本恰好出现一次。
- 初始化一次，之后 200 轮；种子 101、202、303；CPU、单线程 BLAS。
- 主场景 scale=0.08，跑 A/B/C/D，共 12 次方法运行；边界场景 scale=2.0，只跑 A/D，另加 6 次。
- 初始权重为标准高斯除以 sqrt(d)，初始偏置为 0。每轮权重加入标准差 scale/d 的独立高斯扰动，偏置加入标准差 scale/20 的扰动。这与旧微基准的扰动尺度定义一致；scale 不是学习率。

同一场景、种子内，所有方法共享只读特征、图和当前参数快照，缓存和提交参照相互独立。场景之间使用相同初始状态和标准正态扰动序列，再按不同 scale 缩放。每轮轮换方法运行顺序，不并行计时。

## 运行

在工作区根目录使用 Python 3.10+：

```powershell
python -m pip install -r experiments/overhead_benchmark/requirements.txt
python -m unittest experiments.overhead_benchmark.test_benchmark -v
```

已有 NumPy、threadpoolctl 时不用重新安装。先跑小规模检查：

```powershell
python -m experiments.overhead_benchmark.run --suite all --samples 128 --dimensions 32 32 32 64 64 64 --rounds 4 --seeds 101 --memory-audit --output experiments/overhead_benchmark/results_smoke
```

完整主场景＋独立进程内存测量：

```powershell
python -m experiments.overhead_benchmark.run --suite main --memory-audit --output experiments/overhead_benchmark/results_main
```

仅边界场景，或一次运行全部：

```powershell
python -m experiments.overhead_benchmark.run --suite boundary --memory-audit --output experiments/overhead_benchmark/results_boundary
python -m experiments.overhead_benchmark.run --suite all --memory-audit --output experiments/overhead_benchmark/results_all
```

`--memory-audit` 会在计时结束后，为每个方法／种子启动独立进程，完整回放同样的初始化和 200 轮，仅测内存，因此会增加运行时间。内存回放的耗时不进入性能结果。

## 与现有方法的对应

1. 特征始终固定，只接受当前线性头快照；不更新编码器、不对齐客户端簇编号。
2. 缓存保存真实前向时的 winner、各簇分数差、对应累计变化表行和真实计算轮次。
3. 每次参数变化提取当前头与上一快照之差，累计类别对权重差的 L2 范数与偏置差绝对值。样本用“当前累计量－上次真实前向时累计量”构造候选集合。不能只看最近一步。
4. 两端点候选集合无交集则确定异簇；两者均为同一 singleton 则确定同簇。其他边只重算其中尚未确定标签的端点，先去重。
5. 只有真实前向会刷新样本参照。认证通过不重置参照；一次通信提交也不意味着全部样本重新计算。
6. 硬关系来自上述当前候选判定或真实前向；与客户端上次已提交关系比较后传输。聚合者统计整数同簇票数，C/N 对应当前软目标。
7. 聚合者是客户端 0，它自己的关系参与等权统计，但自身操作不计网络消息。

当前受控实验**不执行本地 K-means、私有训练或学生蒸馏**，这些步骤被预先约定的参数轨迹替代，因此不计入也不声称节省它们的计算。以后加入真实训练时，私有训练和公共蒸馏造成的全部头更新必须进入同一快照序列；收到目标后的带梯度学生前向仍需真实执行，不能借用此处的推理缓存冒充计算图。

## 真实消息和提交状态

`codec.py` 生成并解析实际 bytes：48 字节固定头，包含格式版本、消息类型、编码模式、任期、基准版本、目标版本、发送者、向量长度、记录数和图摘要。向量正文紧凑按位打包：

- 上行全量每边 1 bit；稀疏差分发送边编号和 1 bit 翻转方向。
- 下行全量每边 ceil(log2(N+1)) bit；稀疏差分发送边编号和新计数。
- 无变化仍发带版本的确认消息；ACK、commit 带 16 字节消息／状态摘要。
- 自适应组会实际构造候选消息，按 `len(packet)` 选择较小者。选择、编码、解码、状态复制、摘要和确认的计算均在计时内。
- 第一次必须全量初始化。聚合者额外保留**每个客户端已提交的旧硬关系**，这样单个客户端改发完整新关系时，可以减旧加新；该存储计入内存。只持有总计数的实现不能直接沿用这个全量替换操作。
- 每轮各非聚合客户端有上传、上传接收 ACK、下行、准备 ACK、commit、commit ACK 六条单播消息。所有数据及 ACK 验证完成后统一推进提交参照。缺少任何成员时不执行一轮。
- 初始化额外发送公共 ID 顺序描述和完整边表，确认后计入初始化通信量。公共原始图片／特征是预先准备的合成输入，未测它们的首次获取或特征提取成本。

这里是可靠内存投递的同步状态机，没有网络栈、丢包、重传、网络分区或跨进程部分提交恢复。ACK 失败测试只验证本地事务未推进，不证明分布式故障恢复。

## 计量和校验口径

- `generation_seconds`：头差分提取、累计界、候选集合、图检查、必要前向、去重和缓存维护。
- `exchange_seconds`：真实消息选择、编解码、ACK／摘要、整数计数更新和状态复制；不是链路传输时间。
- `total_measured_seconds`：该方法关系生成＋消息交换的总程序耗时。客户端在本进程串行模拟，因此不是并行 FL 的轮时。
- 初始化单列，同时报告包含初始化的累计耗时／字节，避免只挑稳态。
- `persistent_method_array_bytes` 包括算法缓存、上一个头参数及通信提交状态，不含共享特征和图；共享输入字节另列。它不是整个 Python 进程内存。
- 可选 `memory.json` 给出隔离进程的完整回放峰值：Python／NumPy 的 tracemalloc 峰值和原生进程峰值工作集。包含合成输入和运行时，不能直接解释为认证独占内存。内存测试不含全量 oracle，且不同方法不共存。
- 每轮在计时外另算全量 oracle，逐客户端逐边检查输出、接收关系、聚合计数、各客户端接收计数，并检查当前真实 winner 未被候选集合遗漏。错误立即终止，绝不利用 oracle 修复缓存。
- 认证具有明确的实数上界依据和精确整数性质测试。浮点实现沿用旧原型的 `1e-10` 数值 guard，没有宣称完整 IEEE 舍入证明；每次实测仍需通过全量 oracle。
- B/D 应通信轨迹相同，A/C 应通信轨迹相同；C/D 应前向端点数相同。这些是自动检查的机制隔离条件。实际加速则不保证。

## 输出

- `environment.json`：环境、数值精度、BLAS 线程与范围声明。
- `main_101.json` 等：逐轮、逐客户端前向数量、阶段耗时、编码模式、字节及正确性检查。
- `summary.csv`：每个场景／种子／方法的一行汇总。
- `memory.json`：仅显式加 `--memory-audit` 时生成。

比较 A/B 的字节、A/C 的计算、B/D 的计算和 A/D 的含初始化总阶段成本。JSON 中比较比值均为“前者／后者”，大于 1 表示后者较省或较快。3 个种子仅用于本阶段机制验证，不足以支撑普适加速或学习效果结论。
