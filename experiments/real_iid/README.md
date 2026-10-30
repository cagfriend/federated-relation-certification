# 真实数据 IID：冻结编码器的关系协作与开销实验

此实验按现有 TXT 实现真实训练，不启用 research-rigor 或其他 skill，不修改原 TXT 和旧开销实验。

## 要验证什么

1. B 与 Local：公共硬关系协作是否有学习价值，是否出现簇塌缩。
2. D 与 B/E：自然训练更新下，关系认证能否省算、完整头训练流程是否省时。
3. B/E/D：每轮关系、聚合计数、通信轨迹和学生更新后头参数是否一致。
4. 计算收益的空间代价，以及加入一次性准备成本后还剩多少收益。

本轮为 IID，模型同属单隐层 MLP 家族，隐层宽度不同。选择 MLP 是首个可运行实例，不将方法限定为 CNN。初始聚合者是现有客户端 0，稳定成员期间固定；使用旧协议的真实应用层字节编解码，尚无实际 socket、选举协议、掉线或故障恢复。不会把串行模拟耗时写成并行 FL 轮时，也不测能耗。

## 环境与运行命令

推荐继续使用已检查的 Anaconda 环境：Python 3.12.7、NumPy 1.26.4、SciPy 1.13.1、scikit-learn 1.5.1、PyTorch 2.7.1。已存在这些依赖时不用安装；代码不依赖 torchvision。

**必须先切换到工作区根目录**，避免 `No module named experiments`：

```powershell
Set-Location -LiteralPath 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
```

缺依赖时才安装：

```powershell
& 'D:\anaconda\python.exe' -m pip install -r experiments/real_iid/requirements.txt
```

先做真实数据快速检查（64 公共样本、2 个小模型、3 轮、1 种子，包含4个隔离内存回放）：

```powershell
& 'D:\anaconda\python.exe' -m experiments.real_iid.run --preset smoke --download --memory-audit --output experiments/real_iid/results_smoke
```

快速检查完成后，正式实验（6 客户端、200 轮、3 配对种子，共12次方法训练＋12次独立内存回放）：

```powershell
& 'D:\anaconda\python.exe' -m experiments.real_iid.run --preset full --download --memory-audit --output experiments/real_iid/results_full
```

如果要使用本机 GPU **加速编码器准备**，可在上述命令增加 `--prepare-device cuda`。聚类头 SGD、认证和消息处理仍统一在 CPU float64 上运行，避免混入 GPU/CPU 转移差异。默认准备阶段为 CPU；两种设备生成不同准备缓存，不能在同一批结果中切换。所有方法复用已保存的同一批特征。

`--download` 只下载三个所需的官方 IDX gzip 文件并核对官方 MD5；不读取真实训练标签。原始数据放在 `experiments/real_iid/data/`，准备缓存放在 `experiments/real_iid/prepared/`。也可以手动放入官方文件，然后省略 `--download`。官方来源及校验值见 [Fashion-MNIST](https://github.com/zalandoresearch/fashion-mnist)。

正式缓存保存私有/公共/测试的固定特征，默认3种子约需数 GiB 磁盘。用 `.npy` 内存映射读取私有/测试特征，公共特征进入认证前转为 float64。测试指标需要周期性访问测试特征。

输出目录非空时会拒绝覆盖。中断后按原计划接续：

```powershell
& 'D:\anaconda\python.exe' -m experiments.real_iid.run --resume --output experiments/real_iid/results_full
```

接续使用已保存的配置、路径、种子、设备和内存设置，不需要重写其他参数；源码和依赖版本必须相同。完成的种子和内存档案保留，未完成种子从头重跑。seed结果和内存档案带内容校验值，能检测仍为合法JSON的意外修改。损坏的 JSON 或未完成的特征准备缓存会拒绝自动覆盖；可选新的缓存/输出目录或先检查部分文件。准备耗时不短，提前中断时可能需要重做当前种子的特征准备。

## 固定配置

| 项目 | 正式配置 |
|---|---|
| 数据 | Fashion-MNIST；train 60000 / test 10000；训练不使用真标签 |
| IID 划分 | 每种子随机抽4096个公共样本，剩余55904全部分配：9318、9318、9317、9317、9317、9317；无重复/遗漏 |
| 模型 | 各客户端独立无标签去噪 AE：784→width→784；encoder 为 Linear+ReLU；宽度512×3、2048×3 |
| 编码器准备 | 仅本客户端私有图像；Adam lr=0.001，5 epoch，batch256；高斯噪声 std=0.15；重建MSE |
| 固定特征 | 预训练后 encoder eval + 禁用梯度；逐样本L2归一化；不在主训练阶段更新 |
| 私有伪标签 | 各客户端一次K-means，K=10，n_init=10，max_iter=100；之后固定 |
| 头 | float64线性头；随机初态；所有方法同客户端初态完全相同；无动量SGD lr=0.1 |
| 每轮私有训练 | 1 epoch，batch128；固定伪标签交叉熵 |
| 每轮公共训练 | 1 epoch，edge batch256；BCE权重1；输入为两端softmax概率内积；使用计数/N软目标 |
| 公共图 | 每种子固定随机匹配图，2048条边，每点度1；同种子方法共用 |
| 训练预算 | 200个真实训练轮；首轮全算建立缓存并同步，之后199轮允许认证；没有额外无训练通信轮 |
| 种子 | 101、202、303；可在新运行时显式 `--seeds ...` |
| 评价 | 每20轮及最终轮，逐客户端NMI/ARI/Hungarian ACC、簇占用和最大簇比例 |
| CPU 头部 | 单线程 BLAS；客户端串行；方法顺序按种子及轮次轮换 |

## 四组及每轮顺序

- Local：只有私有CE；用于诊断协作学习价值。
- B：全量教师前向＋自适应全量/差分。
- E：逐样本候选认证；只重算非singleton；与B相同编码。
- D：关系认证；只重算未决边涉及的未确定端点；与B相同编码。

各组有自己的头、认证缓存、提交状态和优化过程；共享只读数据与固定特征。每个客户端使用相同的批次随机顺序，各方法用独立同种子调度生成器重建顺序，不依赖其他方法消耗了多少随机数。

每轮：私有CE更新 → 复制并冻结本轮教师头快照 → 生成全部约定关系 → 成功提交计数/N → 各学生按自身接收目标执行全新公共前向和梯度更新。解析反向传播与CE/BCE目标对应，开发测试以有限差分核验；学生不使用教师推理缓存冒充梯度。

认证器的 `previous_weights` 始终保留上一次关系生成的教师快照，公共更新后不重置。下一轮教师快照差分包含前一轮公共SGD和本轮私有SGD的净变化；对固定特征线性头，端点参数差的范数上界及跨教师快照三角累计仍成立，不需要假定中间每一步都小。样本参照只在真实前向后刷新。

## 计量和解释

- `training_pipeline_seconds`：方法初始化、私有SGD、快照与认证/前向、协议/软目标构造、真实学生SGD及阶段间开销。首轮建缓存和初始化消息计入。
- `with_shared_preparation_seconds`：C0＋上述成本。C0是共享无标签预训练、特征（含测试）提取、K-means、落盘与共享加载；实际只执行一次，不按4组数量除。它表示从头运行某个方法的成本核算，不是四次单独测量的准备过程。各准备阶段细分见缓存 `prepared.json`。
- oracle、定期指标评价、下载、报告输出不进入方法计时。程序整体运行时包括这些额外工作及可选内存回放，不能把整个进程墙钟当作某一个方法的延迟。
- 生成阶段节省和训练流程净节省都按同种子 D/B、D/E 比值统计，再取中位数、范围和胜出数。不再扫描人为 `scale`，不只报告有利轮次。
- 真实通信 bytes 包括图注册、编号、版本、ACK和commit。B/E/D应完全一致，本实验不会给认证重复计通信压缩收益。
- 内存回放每种子、每方法独立进程跑完整200轮，关闭oracle、保留同样指标评价，耗时丢弃。峰值含输入/运行时/测试评价，不等于认证独占缓存，也不是编码器预训练阶段或GPU峰值。
- 每轮全量oracle在计时外核对关系、上传解码、聚合计数、各端接收计数、真实winner候选成员；另要求B/E/D每轮公共更新后头参数摘要和消息轨迹一致。任何不一致立即停止，无oracle修补。
- 按客户端分别评价再平均；不在客户端间对齐簇编号；Hungarian映射仅用于测试ACC。

IID协作未必提高指标。若B不优于Local或发生塌缩，应先诊断学习目标、预训练和度1图的信号；不能将D省时当作协作有效的证明。后续再独立检查图密度和数据异构。

## 输出与给主AI检验的文件

- `report.md`：自动报告；`summary.csv`：各seed/方法性能与质量；`paired_summary.json`：配对比值与B/Local学习诊断。
- `seed_101.json` 等：逐轮耗时、重算数、学生前向、损失、头摘要、消息轨迹、各客户端指标及正确性计数。
- `memory_*.json` / `memory.json`：独立内存档案；`memory_summary.csv`：各方法跨种子的中位数与范围。
- `environment.json`：配置、解释器绝对路径、依赖版本、BLAS、源码哈希；`prepared_*.json`：缓存路径和清单摘要。
- `completed.json`：全部完成标记。跑完后告诉主AI输出目录即可；主AI检查原始数据，不能只凭自动报告验收。

开发验证：

```powershell
& 'D:\anaconda\python.exe' -m unittest experiments.real_iid.test_real_iid -v
```

开发测试使用明确标记的微型生成特征/IDX夹具，不属于真实 Fashion-MNIST 研究结果；正式12次训练由用户执行。
