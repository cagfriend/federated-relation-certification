# Private workload 实验独立复审

日期：2026-10-31  
复核对象：staging `experiments/private_workload`（下载 commit `00ac416`）及主 AI 已安装的本地修复版本。复核为只读；未训练、下载或改动 staging 源码。

## 结论

- **原始 staging 有一项阻断性校验缺口**：`run.py` 的 `check_case`（staging 第 81 行）只检查伪标签直方图类别数与总量，没有从缓存 pseudo 标签按当轮子集索引重算。因此自洽但错误的 histogram 可以通过独立 case 校验。
- **主 AI 本地补丁已修复该缺口**：新增 `check_private_histograms`，从已准备目录读取每客户端 `client_{c}_pseudo.npy`，依据校验器独立重算的子集 indices 执行 `bincount` 并与记录直方图逐项相等比较；空表/长度不匹配也因比较失败而拒绝。新增单测覆盖正确值、错误 bin 分布及空表。主 AI 报告本地 7 项测试已通过（含 `-W error::ResourceWarning`）。这项修改只增强结果校验，不改变采样、训练或计时路径。
- **可运行判定：可进行本地正式运行**，建议基于补丁后的工作区版本，而不要直接运行未修复的 staging 快照。运行依赖与数据准备按 README 中命令执行；完整正式 run 需官方 smoke 完成后再验收。主 AI 报告 official smoke 正在运行，本复核没有代跑。

## 复核发现

### 设计与抽样

`design.py` 将 M 固定为 16384、公共学生更新固定为每客户端 8 步，比较 full / 2048 / 1024 私有头训练样本上限。正式设计为 2 个划分 × 3 个既有 seed × 3 档；README 将编码器预训练与伪标签继续按完整私有数据准备，故实验边界是“减少私有头 SGD 工作量”，不能解释为减少了用于编码器训练的数据。

`sampling.py` 为每个 `(seed, client, round)` 使用独立 SeedSequence 流 403；full cap 走原 `private_epoch`，受限档对每轮随机排列的前缀做 SGD。代码和测试支持可重复、方法无关的子集。**跨多轮覆盖完整私有集是概率倾向，不是保证**；不得将注释中的“仍覆盖完整集”当作有限轮次确定性保证。主 AI 计划另做 200 轮实际覆盖审计，这适合作为补充证据。

### 引擎、公共图与 B/E/D 公平性

`engine.py` 仅更换每轮私有 SGD 输入。教师关系仍对完整约定图生成、编码、交换和聚合；公共学生在当前参数上按冻结 schedule 取固定边数执行。验证模式逐轮比较 B/E/D 头摘要、私有损失/子集摘要/样本量/伪标签 histogram、公共损失、公共调度和 optimizer 记账，并运行全图关系与候选 oracle。full 私有档复用原始 `private_epoch`，测试将其与 `public_budget` 引擎逐轮对账。整体设计满足同配置配对原则。

### 计时与私有工作量记账

私有计时包住 `private_workload_epoch`，包括当轮子集索引生成以及 `features[indices]` / `labels[indices]` 高级索引复制，因此私有阶段计时合理包含受限采样的实际成本。样本端点、每客户端样本数和按 batch 向上取整的 optimizer steps 有显式记账。完整档改由原始函数处理，避免额外索引副本影响历史逐位一致性。

计时为已声明的已知 seed、配对串行 CPU 口径；不是独立 seed、独立进程或真实并行 FL 轮时延。内存审计仅对 full 档隔离回放，峰值是 CPU 进程工作集，回放时间不进入性能比较；README 对范围有说明。

### 护栏、锚点及报告

`report.py` 的质量护栏按同划分、seed、方法配对 full 与 reduced，阈值为 ACC 下降不超过 0.01，并对缺档输出 pending；NMI/ARI 及客户端变化作为描述性数据。`run.py` 会在旧 `public_budget/results_full` 存在且身份匹配时校验 full 档锚点，否则记录未校验，边界明确。`check_case` 对计划、case 身份、图摘要、调度、通信账本、每轮/汇总时间关系、指标均值、coverage、validation 计数及来源哈希做校验。报告声称会独立重算 histogram 在原 staging 未兑现，前述本地补丁补齐。

## 阻断级别与剩余限制

| 项目 | 级别 | 判定 |
|---|---|---|
| staging 伪标签 histogram 仅检查形状和总数 | 阻断 | 已在主 AI 本地版本修复；合并/正式运行应包含此补丁 |
| 有限轮数对子集长期覆盖的表述 | 非阻断、需准确表述 | 随机抽样不保证每个样本实际出现；建议以 200 轮审计量化 |
| 已知 seed、串行计时与 full-only 内存审计范围 | 非阻断、设计限制 | README/设计范围已披露，不应推广成普遍速度或峰值结论 |
| 初次本地依赖/数据/准备环境 | 运行前置条件 | 按 README 官方数据与 CUDA/CPU 配置运行；不影响代码逻辑判定 |

## 验收证据

静态复核源文件：`design.py`、`sampling.py`、`engine.py`、`run.py`、`report.py`、`README.md`、`VALIDATION.md`、`test_workload.py`。已查看主 AI 工作区 `run.py` 的 histogram 重算实现和 `test_workload.py` 的拒绝用例；本复核未执行代码。主 AI 提供的本地验收记录为 7 项测试通过，official 18-case/54-trajectory/18-memory smoke 当时仍在运行，需由主 AI 后续给出最终运行结果。

## 最终补充复核（2026-10-31）

主 AI 后续加入的两项校验已只读核对，均可接受，且不改变训练机制：

1. `run.py` 新增 `public_budget_sources()`，把 `experiments/public_budget/*.py` 的 SHA256 写入冻结环境；`check_environment` 在启动/恢复及结束时重新比对。该目录提供复用的学生更新实现，纳入来源冻结可避免复用依赖漂移却继续验收旧计划。
2. `check_case` 现在将每方法 summary 的私有 optimizer steps、forward endpoints 与逐轮记录总和比较，并要求 summary `private_samples_per_client` 等于本档每客户端有效样本数。这样补足了逐轮账本已校验、汇总账本仍可能被篡改的缺口。

我确认上述代码位于本地 `experiments/private_workload/run.py`（来源冻结约第 31、157 行；汇总核对约第 113 行）。未执行测试、smoke 或正式训练。主 AI 通报完整本地 smoke 已完成 18 case、54 trajectories、18 memory replays；这属于主 AI 提供的运行证据，不是本复核亲自运行或独立验证的结果。其 `audit_local.py` 对 51 文件、缓存重生成及 200 轮子集覆盖的审核仍在进行，待该审计完成再验收审计项；覆盖结果仍应按随机抽样的实测统计解释，不能视为设计保证。

**更新结论：** 两项新增来源/汇总校验补强合理；补丁版可运行性判断维持。正式实验结果与审计通过情况不在本复核结论范围内。
