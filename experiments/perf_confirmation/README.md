# 独立性能确认实验（perf_confirmation）

对应 `docs/NEXT_EXPERIMENTS.md` 第 2 项，设计在执行前冻结于
[`PREREGISTRATION.md`](PREREGISTRATION.md)，与本目录代码同提交。

## 要确认什么

私有头部工作负载实验（第 1 项）的候选配置——M16384、公共固定 8 步、
每客户端每轮私有上限 **2048**——在探索中得到 D/B 完整头省时约 22%、
D/E 约 3–5%。但那是旧 seed（404/505/606）、同进程轮换执行的探索性
证据。本实验换新 seed（707/808/909）、改为**单方法独立进程**、
每运行 2 次技术重复，按预注册的 C1/C2/C3 规则机械判定候选档的计算
收益是否成立。质量只作护栏（相对完整档 ACC 下降 ≤1 个百分点），
判定不要求 ACC 提高。1024 档已证明质量不可接受，不纳入。

## 与既有实现的关系

训练实现不新写：直接复用 `experiments/private_workload` 的冻结引擎
（私有抽样日程、公共学生、协议、认证均未改）。其全部随机流由
(seed, client, round) 显式播种，联合运行本就断言 B/E/D 同轨迹，
因此单方法进程可复现其在联合运行中的同一条轨迹；本实验在组级
（3 方法 × 2 重复 = 6 次运行）用非计时字段逐轮核对这一点，
不一致即停、组计时无效。计时口径与既有实验一致：进程内
`head_pipeline_seconds`（含初始化，不含准备/加载/审计/评估）；
进程总墙钟与峰值内存另行描述性记录。串行单线程执行。

## 运行

```powershell
# 正式（新 seed 的准备缓存不存在，首次会做 AE 预训练 + KMeans）
D:\anaconda\python.exe -m experiments.perf_confirmation.run --preset full --prepare-device cuda --download
# 中断后续跑（已完成运行经校验保留，单次运行整体重跑）
D:\anaconda\python.exe -m experiments.perf_confirmation.run --preset full --prepare-device cuda --download --resume
# 云端/开发自查
python -m experiments.perf_confirmation.run --preset smoke
```

预计总墙钟约 2.7–3.2 小时（估计：纯方法计时约 2.2 小时 + 6 组新
seed 准备 + 72 次进程启动/加载与审计评估开销）。无内存回放
（内存问题属第 5 项，本实验只记录每次运行的进程峰值）。

## 输出（results_full/）

- `runs/<...>.json`：72 次独立运行的密封记录（逐轮计时与轨迹字段）
- `runs.csv` / `seed_summary.csv`：逐运行与 seed 层（重复平均）耗时
- `paired_cost.csv` / `paired_summary.csv`：逐 seed 配对比与中位/范围/胜出
- `timing_noise.csv`：同 seed 两次重复的相对计时差
- `quality_guardrails.csv`：2048 相对完整档的 ACC 护栏（逐划分 × seed）
- `report.md` / `summary.json`：含预注册判定表（C1/C2/C3，两划分）
- `completed.json`：72 次运行、12 组轨迹核对、mismatches=0 的完成凭据

剔除规则只有一条且已预注册：用户确认的休眠/暂停按（划分 × seed）
共同轮掩码处理，原始记录保留；其余一律全计。
