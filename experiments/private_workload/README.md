# 减少私有头部训练工作负载

本轮主问题是：在公共参考图和学生更新预算固定时，减少每轮私有头部 SGD 处理的样本量，能否提高关系生成在总流程中的占比，并放大 D 相对 B/E 的整体净省时。质量只作护栏，允许减少私有预算导致小幅下降，不要求协作质量提高。

这是 `docs/NEXT_EXPERIMENTS.md` 第 1 项。公共库规模与学生预算解耦已由 `public_budget` 完成；本轮固定其 `m16384_fixed8` 配置，只改变私有工作负载。私有训练数据划分、编码器和伪标签不变。

## 正式配置

Fashion-MNIST；IID 和容量约束 Dirichlet α0.1；三个既有 seed 404/505/606。六客户端宽度 512×3/2048×3，私有共 43616 张，约 7269/7270 张/客户端；各划分私有无标签 AE 预训练 5 epoch 及一次 KMeans 后冻结编码器。公共池 16384，degree1，K10，头部 200 轮。公共 BCE weight1、batch256、学习率 0.1；私有 batch128、每轮 1 epoch（受上限约束时为上限样本的 1 epoch）。

|case_id|公共样本 M|每客户端每轮公共更新|每轮私有上限/客户端|每客户端私有步数（约）|
|---|---:|---:|---:|---:|
|m16384_fixed8_privfull|16384|8 batch|完整私有集|57|
|m16384_fixed8_priv2048|16384|8 batch|2048|16|
|m16384_fixed8_priv1024|16384|8 batch|1024|8|

2 划分 × 3 seed × 3 私有档位 ＝ 18 组；每组实际训练 B/E/D，共 54 条轨迹。三档共享同组私有/公共池/编码器/伪标签及初始头；不复用训练后的头。

## 每轮机制与抽样日程

1. 私有更新：上限为完整时直接调用冻结核心的原始 `private_epoch`，与既有实验逐位一致。上限小于客户端私有量时，先按冻结日程抽取子集，再对子集调用同一个 `private_epoch`。
2. 抽样日程：子集由独立随机流 `SeedSequence([seed, 403, client, round])` 的排列前缀给出（401 为私有洗牌、402 为公共洗牌、403 此前未被使用）。每轮重新抽取，长期仍覆盖完整私有集；只减少每轮工作量，不固定丢弃任何样本。抽取只依赖 seed/客户端/轮次/私有量，不依赖方法，B/E/D 每轮消费完全相同的私有输入；逐轮记录实际样本量、子集摘要和子集伪标签直方图，并由 `run.py` 独立重算校验。
3. 冻结本轮教师快照。B 全量公共前向；E 逐样本认证；D 关系认证，无法认证时精确回退。全部方法对整个约定图生成、编码、交换和聚合关系，学生接收完整计数/N。
4. 公共学生沿用 `public_budget` 的固定预算实现：按 `[seed,402,client,round,0]` 随机流打乱完整图边序，精确取前 8×256 条边执行 8 步。学生始终在当前参数上做新前向。

同配置 B/E/D 使用相同私有子集日程及公共抽边日程，逐轮参数、损失、学生更新步数/端点、接收目标摘要和消息字节必须一致；每轮全图 oracle 验证关系、候选赢家和每个学生收到的完整目标。

全量档另与 `public_budget` 的历史 `m16384_fixed8` 结果做锚点校验（当 `experiments/public_budget/results_full` 存在且配置/准备身份一致时）：逐轮头摘要、traffic、公共步数/端点、public loss、持久数组和全部评估指标必须逐项相等。历史结果不存在时记录 `checked=false`，不强行复用。

**命名边界**：本实验只减少私有*头部* SGD 的每轮样本量。编码器仍由完整私有集预训练，准备成本 C0 按完整口径计入，所以不能称为“小私有数据集”实验；真正的小私有数据需要另做对应预训练或使用来源清楚的独立预训练编码器。

## 主要比较与质量护栏

**主要指标**是同配置、同 seed 的 D/B 与 D/E 完整头部耗时、含共享准备耗时和绝对省秒。生成耗时及占比、私有/公共阶段占比、教师真实刷新比例解释收益来源；持久数组、可选进程峰值和消息字节同时报告。先逐 seed 配对，再取三个 seed 中位和胜出次数，客户端不充作独立 seed。

`workload_effects.csv` 另报同划分/seed/方法下 reduced 对 full 的阶段成本变化。减少私有预算本身带来的省时不能算成 D 认证的贡献；认证收益只由同档位下 D/B 和 D/E 衡量。

质量护栏：同划分、同 seed、同方法，以 reduced 档最终平均 ACC 对 full 档作差。下降 ≤0.01（1 个百分点，含 1e-12 舍入容差）为护栏内；逐方法报告，NMI/ARI、最差客户端和同客户端最小变化另列。超过护栏也完整保存，不中途挑掉配置；护栏是容忍范围而非要求提高。正式检查要求三指标完整；人为不完整报表输入会同时给出 pending 状态，需看状态列，不解释为正式验收。

不同私有档位会改变训练轨迹，允许其质量不同；认证自身在相同配置内必须保持 B/E/D 一致。测试每 20 轮及最终评估，保留曲线及簇占用，不选最好轮次。

## 计时与资源口径

每轮从私有 SGD 前至公共 SGD 后使用整段秒表；包括子集抽取、教师快照、认证/精确回退、完整图消息交换和公共 SGD。加方法初始化得到 `head_pipeline_seconds`。oracle/coverage/评估/摘要在外，完整调用实际等待时间因此大于单方法列。

`with_shared_preparation_seconds` 另加本组最大公共池准备成本和特征载入。C0 包含 AE、全 16384 池/私有/测试特征、KMeans 和写盘；每方法完整计入，不按 3 方法摊薄，不因复用现有缓存记为零，也不视为每个配置的最小独立冷启动成本。注意 C0 始终对应完整私有集预训练，与私有头部档位无关。

配对主运行 B/E/D 共存、顺序按 seed 和轮次轮换。使用三个既有 seed，属于适用场景探索，不是独立新 seed/单方法进程性能确认，也不是实际并行 FL 轮时延。静态选路复核的暂缓安排不变。

持久方法数组范围沿用原核心：头参数、候选缓存及协议数组，排除共同特征/图、Python 对象、覆盖观察器和瞬时临时数组。可选 memory-audit 只对全量私有档，分别隔离 B/E/D、两个划分、三个 seed，共额外 18 条完整训练回放。它们关闭 oracle/评估/覆盖，最终头摘要及持久数组与配对结果对账，只取 CPU 进程峰值工作集，**其耗时不用于性能比较**。不测 AE 准备峰值或 GPU 显存。

三方法使用相同自适应完整/差分/无变化编码，同配置通信相同，不预设新增通信压缩。固定 leader0、全员在线、可靠内存交付，未接恢复协议。

## 运行

在工作区根目录执行正式实验：

```powershell
cd C:\Users\tjp\Documents\Codex\2026-10-14\new-chat
D:\anaconda\python.exe -m experiments.private_workload.run --preset full --prepare-device cuda --download --memory-audit
```

输出 `experiments/private_workload/results_full`。主实验 54 条轨迹；`--memory-audit` 额外 18 条隔离回放，可省略此选项仅跑主实验并报告持久数组。旧缓存不存在时重新准备；CPU 准备需显式 `--prepare-device cpu` 及新输出，不假称复用旧 CUDA 身份。

中断后在同一条命令末尾添加 `--resume`。保存配置、种子、运行库、源码和内存选项冻结；完整 case 保留，未完成 case 从第一轮重做。末尾必须出现 `Finished` 及 `completed.json`，才算 18 组全部完成。

开发路径验证：

```powershell
D:\anaconda\python.exe -W error::ResourceWarning -m unittest experiments.private_workload.test_workload -v
D:\anaconda\python.exe -m experiments.private_workload.run --preset smoke --memory-audit
```

smoke 仍使用官方数据：训练 1024、测试 128、宽度 32/64、公共池/实际样本 128、AE 1 epoch、头 3 轮、公共 batch16、固定 1 步；私有档位按比例缩为完整/128/64，只验证路径，不提供正式性能或质量结论。同样 18 组 54 轨迹，可选 18 个内存回放。

## 输出与证据

- `environment.json`、`completed.json`：冻结设计/来源和全部结果文件哈希。
- 每 case JSON：逐轮整段/分段耗时、私有子集样本量/摘要/伪标签直方图、目标/参数/调度摘要、完整图关系与候选检查、完整评估和覆盖轨迹。
- `summary.json/csv`、`paired_cost.csv`：同配置 D/B、D/E 成本比、绝对省秒、生成占比及资源代价。
- `workload_effects.csv`：减少私有工作负载与完整档位之间的成本变化，单列归因。
- `quality_guardrails.csv`、`final_clients.csv`：逐方法的允许小幅质量下降护栏及逐客户端数据。
- 可选 `memory_summary.csv`：独立单方法进程峰值；不替代计时证据。

旧 public_scaling、noniid_clustering、public_budget 源码及结果不改动。
