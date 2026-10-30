# 半分布式异构联邦聚类：关系认证与自适应传输

原始逐轮大JSON以无损ZIP保存，解压即可恢复原路径；汇总与代码直接可读。见[归档与恢复说明](archives/README.md)。

研究快照：2026-10-30。本文档对应当前方法与已保存的实验结果，仓库用于私有研究备份。

客户端通过公共无标签样本对的“是否同簇”硬关系交换知识。聚合者累加各客户端的判断，返回同簇比例供本地公共关系训练。模型参数不直接平均，因此客户端可以使用同模型家族的不同宽度或特征维度。

当前优化用保守候选簇集合认证样本对关系，仅对无法认证的必要端点重新计算教师预测；上传和下发都自适应选择完整向量、变化列表或无变化确认。当前已验证实现为冻结 MLP 编码器与可训练线性聚类头，不能把实验结论直接推广到持续更新的整个网络。

## 阅读入口

- [方法与每轮流程](docs/METHOD.md)：聚合什么、如何认证、基线区别和实现限制。
- [已经完成的实验](docs/EXPERIMENTS.md)：配置、结果、证明范围与未解决问题。
- [后续实验计划](docs/NEXT_EXPERIMENTS.md)：优先做图密度，再处理机制增量、编码器更新和数据异构。
- [运行与证据说明](docs/REPRODUCIBILITY.md)：当前代码运行方式、结果核验及历史脚本删除说明。
- [最新公共库规模审阅](outputs/public_scaling_results_20261030/RESULTS_REVIEW.md)。

## 当前结果概览

B=全量教师计算，E=逐样本认证，D=关系认证；三者使用同一自适应传输编码。以下是同配置、同种子配对后取三个种子的中位数。

| 公共样本数 | D/B 关系生成耗时减少 | D/B 完整头部训练耗时减少 | D/E 完整头部训练耗时减少 |
|---:|---:|---:|---:|
| 4,096 | 68.50% | 5.81% | 1.29% |
| 8,192 | 72.96% | 9.50% | 0.93% |
| 16,384 | 66.01% | 11.39% | 1.36% |

此实验固定私有数据43,616张、公共候选池16,384张、六个客户端、10簇、degree=1图，运行200轮、三个种子，共27次方法训练。全部配置内B/E/D的逐轮参数摘要、通信记录及已记录评估一致。扩大公共库同时增加图边数和公共学生更新步数。

关系认证没有在共同编码基础上进一步压缩通信。它需要额外内存：最大规模下，六客户端合计的持久方法数组比B多25.35 MiB。上述训练耗时是冻结编码器后的头部训练流程，排除编码器准备、评估、oracle审计及真实网络等待。

## 核心代码

唯一当前实验入口：`python -m experiments.public_scaling.run`。

| 文件 | 作用 |
|---|---|
| [certification.py](experiments/public_scaling/certification.py) | 候选簇集合、逐样本/关系认证及精确回退 |
| [codec.py](experiments/public_scaling/codec.py) | 位打包、完整/差分/空消息及严格解码 |
| [protocol.py](experiments/public_scaling/protocol.py) | 关系计数、上下行提交和消息成本 |
| [head.py](experiments/public_scaling/head.py) | 私有CE与公共关系BCE梯度更新 |
| [engine.py](experiments/public_scaling/engine.py) | 配对训练、逐轮oracle和参数摘要核验 |
| [run.py](experiments/public_scaling/run.py) | 缓存、恢复、结果复用和隔离内存回放 |

四个已验证核心模块（certification/codec/protocol/head）从旧实现原样迁移，保留字节级哈希证据。用户已要求删除的旧实验驱动脚本没有恢复；历史结果仍保留，见 [复现边界](docs/REPRODUCIBILITY.md)。

## 最小运行

在仓库根目录运行（Python环境需安装依赖）：

```powershell
python -m pip install -r experiments/public_scaling/requirements.txt
python -m unittest experiments.public_scaling.test_scaling -v
python -m experiments.public_scaling.run --preset smoke --suite all --download --memory-audit --output runs/smoke
```

数据集、预训练模型和特征缓存未上传。首次运行可用 `--download` 获取官方Fashion-MNIST，并按代码校验摘要。正式配置与下一阶段命令见[运行说明](docs/REPRODUCIBILITY.md)。

当前不宣称：新颖性已获完整文献排重证明、基础协作目标已经稳定优于Local、编码器持续更新已经验证、数据非IID已经验证、真实临时聚合者选举/掉线恢复已经实现、能耗已实测。
