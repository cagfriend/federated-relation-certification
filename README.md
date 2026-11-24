# 半分布式异构联邦聚类：精确关系生成与资源优化

客户端在同一公共无标签样本图上交换「两个样本是否同簇」的判断。聚合者汇总判断并返回同簇比例，各客户端用自己的模型学习这些关系。客户端可使用不同宽度的表示和各自的簇编号。

本项目的主要贡献是在**固定表示和教师快照**下减少生成硬关系所需的计算。全图方法 D 用样本的候选簇直接判定一部分边，只对未解决边的必要端点重算。实验在相同教师关系、学生目标和训练轨迹下比较成本。完整推导见[关系认证](docs/method/relation_certification.md)。

## 阅读导航

[主要结果](#主要结果) · [基础方法](#基础方法聚合什么如何训练) · [适用边界](#适用范围与实现状态) · [代码与复现](#代码与复现) · [实验索引与历史](#实验索引与历史)

## 主要结果

| 研究问题 | 已观察到的结果 | 证据 |
| --- | --- | --- |
| 全图 D 在 STL-10 上何时省时？ | M4096 下，D 对全量 B 的完整头部省时通过两种划分的新种子确认。12 个配置中，D 均为按平均耗时排序最快的全图方法。 | [E54 同界对照](docs/evidence/MATCHED_BASELINES_AND_FASHION_MNIST_20261123.md#e54-stl-10-的全图与按需对照) |
| Fashion-MNIST 结果是否一致？ | E55 原版 D 对同界逐样本 E 的完整头部省时通过两种划分确认。对全量 B，六组平均完整头部耗时均更长。E57 缓冲区复用版 D 在三个 IID 新种子上对 B 省时 **4.91%–8.21%**，强非 IID 下平均耗时与 B 接近。 | [E55 对照](docs/evidence/e55_fashion_confirmation/report.md) · [E56–E57 归因与确认](docs/evidence/FASHION_MNIST_GATHER_OPTIMIZATION_20261123.md) |
| 学生只使用部分边时，通信和时间如何取舍？ | E54 显式 Demand 在 11/12 组平均快于全图 D，应用层字节中位数高 29.6%。E59 仅聚合者重建比显式 Demand 少发 **20.37%** 字节，**11/12** 组通过完整头部耗时门槛。E58 各端独立重建少发 **48.20%** 字节，相对显式 Demand 完整头部增时 **5.19%–10.54%**。 | [E54 按需对照](docs/evidence/e54_paired_boundaries/report.md) · [E58–E59 通信与计时](docs/evidence/DEMAND_SCHEDULE_PROTOCOLS_20261124.md) |
| 计算优化是否改变学习质量？ | 已审计的同配置 B/E/D 轨迹中，关系、目标和训练更新一致。早期 STL-10 设置下三者均曾出现严重退化。E09 对跨客户端协作收益的预设主筛查未通过。 | [结论与边界](docs/RESULTS.md) · [单簇风险](docs/method/stability.md) · [E09](docs/evidence/EXPERIMENT_INDEX.md#e09) |

完整头部耗时包含方法初始化、私有头训练、教师生成、关系交换与公共头更新。共同预训练和特征准备、审计及评估另计。通信量按应用层序列化消息计账。不同协议、批次和工作负载的结果按原实验口径解释。[测量与实现说明](docs/method/implementation.md) · [完整结果](docs/RESULTS.md)

## 基础方法：聚合什么、如何训练

各客户端先用私有无标签图像训练自编码器，冻结编码器后在本地特征上运行 KMeans，得到固定伪标签。历史基础协议采用随机头初始化，后续 STL-10 快照协议使用中心初始化和私有伪簇频数校正。[学习协议](docs/method/learning_protocol.md) · [编码器快照筛选](docs/method/encoder_snapshot_selection.md)

固定公共图的样本身份、顺序和边编号。客户端 $c$ 用自己的教师头预测公共样本的标签 $y_{c,i}$，对边 $e=(i,j)$ 给出同簇判断 $r_{c,e}$。聚合者汇总为

$$r_{c,e}=\mathbf{1}[y_{c,i}=y_{c,j}],\qquad n_e=\sum_c r_{c,e},\qquad \tau_e=n_e/N.$$

等权计数包含客户端自身。六个客户端中有四个判断同簇时，返回计数 4，学生使用软目标 $4/6$。模型参数、梯度和簇编号留在各端。

每轮先用固定私有伪标签执行交叉熵更新，再冻结该轮教师快照并生成边关系。聚合者提交计数后，每个学生批次都用当前头重新前向。学生用两个端点的预测概率内积作为同簇概率，并以目标 $\tau_e$ 计算 BCE 后更新头。[每轮时序、损失和梯度](docs/method/learning_protocol.md) · [训练引擎](experiments/public_scaling/engine.py)

## 关系认证：为什么不知道标签，也能知道关系

| 路径 | 教师关系生成 |
| --- | --- |
| **B · 全量打分** | 每个公共样本打分一次，再由标签生成整图边关系。 |
| **E · 逐样本认证** | 用候选簇认证单个样本的标签，对非单例候选重算。 |
| **D · 按边认证** | 用候选簇直接认证边关系，对未解决边所需的非单例端点去重后重算。 |

固定特征 $z_i$ 时，样本上次真实打分的赢家和分差可以复用。当前 D 用类对权重变化的累计范数与类间偏置的有符号净变化约束分差，排除无法超越旧赢家的簇。实数精确运算下，保留平局即可使真实赢家落在候选集合中。

若边的两端候选不相交，可直接判为异簇。若两端候选都是同一个单例，可直接判为同簇。比如候选分别为 $\{1,2\}$ 和 $\{3,4\}$ 时，D 可以确定这条边为异簇，E 仍需确定两个标签。只有真实打分才更新样本的缓存参考，下一次比较也会计入前一轮公共更新和本轮私有更新。[证书推导、公式与缓存规则](docs/method/relation_certification.md) · [默认生成入口](experiments/public_scaling/generation.py)

<a name="自适应传输什么时候发全量什么时候发变化"></a>
## 全图通信与按需协议

**全图 B/E/D** 共享自适应编码。首轮发送完整向量，随后按与最后已提交状态的实际编码包长度选择全量、差分或无变化确认。聚合者维护逐端关系与整数计数，在版本和摘要校验后推进提交参考。同轨迹下 B/E/D 字节相同。[编码与提交](docs/method/communication.md) · [消息编解码](experiments/public_scaling/codec.py)

**Demand** 在各学生请求的并集上生成关系，按每端原有顺序返回本轮需要的计数。三种实现共享按需投票与目标返回流程，区别在请求和并集如何分发。

| 场景 | 对应方案 |
| --- | --- |
| 每轮需要完整图的计数或已提交状态 | **全图 D**。 |
| 聚合者无法提前重建学生请求 | **显式 Demand**。各端上传请求，聚合者广播并集。 |
| 日程可共享，且要兼顾时间与通信 | **仅聚合者重建**。省去请求上传，保留并集广播。 |
| 应用层字节优先，可以承担重复计算 | **各端独立重建**。各端由公共日程重建并集。 |

这些是已测工作负载下的选择条件。共享日程依赖一致的图、公共样本身份与顺序、固定成员、种子和采样器版本。[协议与选择边界](docs/method/communication.md#按需关系协议)

## 适用范围与实现状态

- **数据与模型。** Fashion-MNIST 和 STL-10 使用独立训练后冻结的异宽 MLP 编码器与可训练线性聚类头。已测数据异构涵盖 IID、容量约束的 Dirichlet 类别偏斜及固定总量下的私有数量不均。正式对照在同一配置内使用相同簇数。当前位集合实现支持 1–64 簇，主协议支持 2–255 客户端。[学习与异构设置](docs/method/learning_protocol.md)
- **计算与数值。** 实数证书依赖冻结特征和线性头。已发表的浮点一致性限于受测轨迹，极端前缀累计与相消有已知反例。净省时依赖参数更新、候选规模、图密度及教师生成占总时间的比例，认证缓存会占用额外内存。[正确性回退](docs/evidence/D_AND_NUMERICAL_FALLBACK_20261122.md#正确性回退) · [成本与口径](docs/method/implementation.md)
- **学习稳定性。** 快照筛选、中心初始化、私有伪簇频数校正和公共步数控制应用于对应的 STL-10 协议。间隔保护是可选项，仍需关注早期和最差客户端的簇集中。[快照筛选](docs/method/encoder_snapshot_selection.md) · [单簇风险与干预](docs/method/stability.md)
- **执行与恢复。** 主训练采用 CPU float64、单线程 BLAS、固定聚合者和成员、可靠串行内存消息。临时聚合者选举和重新选举是框架设计。已有交接恢复证据来自独立合成回放，完整模型状态恢复和真实网络行为仍待验证。应用层字节不含公共数据分发和传输层开销。[聚合者与恢复](docs/method/aggregation_recovery.md) · [通信统计范围](docs/method/communication.md)

## 代码与复现

在克隆后的仓库根目录运行以下命令。最后一条是开发短测。正式结果使用各实验包的指定配置、输入和审计流程。

```powershell
python -m pip install -r experiments/public_scaling/requirements.txt
python -m unittest experiments.public_scaling.test_scaling -v
python -m experiments.public_scaling.run --preset smoke --suite all --download --output runs/smoke
```

| 入口 | 内容 |
| --- | --- |
| [完整复现说明](docs/REPRODUCIBILITY.md) · [实验代码导航](experiments/README.md) | 依赖、数据准备、历史缓存与重跑边界。 |
| [E54 STL-10 同界对照](snapshot_routing/paired_boundaries/README.md) · [E55 Fashion-MNIST 确认](snapshot_routing/fashion_confirmation/README.md) | B、同界 E、D 与适用的按需对照。 |
| [E56 阶段归因](snapshot_routing/fashion_generation_profile/README.md) · [E57 缓冲区复用](snapshot_routing/fashion_gather_optimization/README.md) | 特征收集开销、筛选和新种子确认。 |
| [E58 各端重建](snapshot_routing/shared_schedule_demand/README.md) · [E59 仅聚合者重建](snapshot_routing/leader_schedule_demand/README.md) | 按需协议的通信拆账、完整头部计时与轨迹审计。 |

原始数据、模型和特征缓存由复现流程准备。历史运行记录、部分已归档驱动的可用性和原机缓存要求见[历史源码台账](docs/evidence/CODE_HISTORY.md)与[原始记录归档](archives/README.md)。

<a name="已完成验证及其解释"></a>
<a name="信息保留来源和后续计划"></a>
## 实验索引与历史

- **按问题审阅** · [结论与适用边界](docs/RESULTS.md) · [主张与证据对应](docs/evidence/CLAIMS.md) · [方法专题](docs/METHOD.md)。
- **按实验编号审阅** · [实验与证据总索引](docs/evidence/EXPERIMENT_INDEX.md) · [原始记录归档](archives/README.md) · [后续实验](docs/NEXT_EXPERIMENTS.md)。
- **追溯原有叙述** · [重整前的完整 README](https://github.com/cagfriend/federated-relation-certification/blob/9dc5c98290a9f986d1b420644efb4585c66748c2/README.md) · [历史累计偏置 D 的计时汇总](https://github.com/cagfriend/federated-relation-certification/blob/9dc5c98290a9f986d1b420644efb4585c66748c2/README.md#4-历史累计偏置-d-的实验收益) · [历史验证表与负结果](https://github.com/cagfriend/federated-relation-certification/blob/9dc5c98290a9f986d1b420644efb4585c66748c2/README.md#已完成验证及其解释) · [伪代码与示例](https://github.com/cagfriend/federated-relation-certification/blob/9dc5c98290a9f986d1b420644efb4585c66748c2/README.md#完整伪代码与基础实现示例)。
- **追溯方法来源** · [原始方法笔记](docs/history/user_method_notes_20261109.utf8.txt) · [来源映射](docs/history/SOURCE_MAP.md) · [历史版本与快照](docs/history/README.md)。
