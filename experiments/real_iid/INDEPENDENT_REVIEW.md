# 独立代码审阅：真实数据 IID 实验

## 范围

审阅对象为 `experiments/real_iid/` 中的 `config.py`、`data.py`、`head.py`、`engine.py`、`run.py`、`report.py`、`test_real_iid.py`、`README.md` 和 `requirements.txt`，以及所复用的 `experiments/overhead_benchmark/certification.py`、`protocol.py`、`codec.py`。

本次只做独立静态审阅和小规模开发验证；未下载 Fashion-MNIST、未运行真实数据 smoke/full 实验，未改实现代码、原 TXT 或旧实验。单元测试中的 IDX 与特征均为明确标记的微型 fixture，不能当作真实数据结果。

## 审阅结论

截至本次复查，未发现阻断实现或会直接使计划实验结论失真的错误。梯度、训练顺序、关系认证状态更新、协议调用和成本归属与文档描述基本一致。结论只覆盖源码及 toy fixture 验证，不证明真实 Fashion-MNIST 上的质量、性能、数值稳定性或长时间运行表现。

## 证据与核对结果

- 指定命令 `D:\anaconda\python.exe -m unittest experiments.real_iid.test_real_iid -v`：**13 项通过**，耗时 7.815 秒。包括私有 CE 与公共关系 BCE 的有限差分梯度检查、重复端点梯度、IID 划分覆盖无重叠、真实训练标签未读取、编码器冻结、公共更新进入下一轮证书参数增量、B/E/D 轨迹与协议一致性、准备身份版本变化、缓存文件损坏拒绝、非空输出保护、合法 JSON 内容变更检测，以及从 SGD fixture 到报告和配对统计文件的贯通检查。
- `head.py` 的公共关系损失对每条边的左右端点分别累计梯度；使用 `np.add.at`，因此重复端点会累加。裁剪后的 BCE 导数与区间外零导数相符。测试覆盖自边及共享端点。
- `data.py` 只读取 train 图像和 test 标签；不读取训练真标签。AE 和 KMeans 输入均来自每个客户端的私有图像/特征；公共和测试标签不参与优化。评估中的标签仅进入 NMI、ARI 和 Hungarian ACC 计算。
- `engine.py` 首轮在真实私有 SGD 后创建全量关系缓存并提交协议；后续每轮顺序是私有更新、固定教师快照、关系生成/提交、学生新前向梯度更新。公共更新后未覆盖 `RelationGenerator.previous_weights`；测试隔离公共更新并确认其出现在下一教师快照的 delta 中。
- 公共特征存盘为 float32，进入 `Prepared.public` 时复制为 float64；用于教师打分、认证和审计的是同一 float64 数组。认证差分可累积公共更新与下一轮私有更新之间的净参数变化。候选成员和全量关系 oracle 在验证路径中逐轮核对。
- `RelationProtocol` 复用旧应用层编码，包含初始化图注册、向量消息、ACK 和 commit；固定 client 0、可靠同步内存投递的边界在源码和 README 中有说明，不应解释为实际 socket、选举或故障恢复实验。
- 每个方法都从相同客户端初始头出发，使用确定性的客户端/轮次批次顺序。B/E/D 在每轮后要求头部 digest 和流量轨迹一致，测试小 fixture 的结果满足条件。
- 计时包括方法初始化、首轮缓存和协议 setup、私有/生成/交换/学生训练。oracle 和指标评估在计时外。`with_shared_preparation_seconds` 使用缓存内原始 C0 准备时间加本次共享特征加载与该方法 T；C0 不除以方法数，并注明 cache reuse 时使用的是原始准备计时，不代表本次重做。Local 被标为质量诊断组。
- 缓存身份修复已复核：准备 key 包含 `data.py`、关系图生成实现 `certification.py` 的 SHA，以及 NumPy、Torch、scikit-learn、SciPy、threadpoolctl 版本；命中时校验身份、配置、seed 和所有已登记文件 SHA。损坏缓存测试通过。
- 内存子进程路径已静态核对：以当前 Python 解释器启动同一模块，读取保存的 environment 与 prepared manifest，在开始 tracemalloc 前重新验证准备文件，再单方法完整回放；计时结果被丢弃，另外记录 Python 分配峰值、进程峰值和方法持久数组大小。真实缓存上的隔离子进程尚未在本次运行。
- 恢复与输出路径静态核对：非空输出目录拒绝新运行覆盖；resume 使用已保存配置/路径/种子；完成种子按结构校验后保留；输出 JSON 用新建模式写入。正式 CLI、下载、内存回放和完整结果文件均未实际执行。

## 复查修订

前一轮提出的两项文档/恢复建议已在本轮代码复查中解决：README 已列出 `memory_summary.csv`；seed 与 memory profile JSON 写入规范化 payload SHA，恢复时会校验，合法 JSON 字段改写测试能拒绝；报告贯通测试还从四方法 SGD fixture 生成 `paired_summary.json` 和 `memory_summary.csv` 并核对配对耗时比。非空输出目录保护也有回归测试。payload SHA 可检测意外改写或损坏；它不是带密钥的防伪签名。

剩余范围限制：未下载或运行真实 Fashion-MNIST smoke/full CLI；未运行真实缓存上的隔离内存子进程。正式数据上的质量、耗时、内存和完整运行恢复仍需用户执行后再审阅输出。
