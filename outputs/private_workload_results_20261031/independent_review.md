# 独立审阅：private_workload results_full

审阅日期：2026-10-31。只读检查 `experiments/private_workload/{README.md,report.py,run.py,engine.py}` 及 `results_full`；独立以 Python 标准库从 CSV/JSON 读取、配对和重算。未改源码和原始结果。审阅范围是完成性、计时/质量/内存口径与异常；不是方法正确性的完整代码审计。

## 结论

- 完成性通过：`completed.json` 报告 18 个 case、54 条训练轨迹、18 次隔离内存回放、0 mismatches；清单内 51 个结果文件逐一重算 SHA-256，均与清单一致。18 个训练 JSON、54 行 `summary.csv`、18 行 `memory_summary.csv` 数量相符。
- 主性能结论有条件成立：同 partition/case/seed 配对后，D 的完整 head 流程（含初始化）相对 B 在 6 个 partition×limit 组、共 18 个 seed 配对中全部胜出。D 对 E 在 1024 档两种 partition 均 0/3 胜出（中位数慢约 0.8–1.6 秒）；2048 与 full 档均 3/3 胜出，但时间优势小。只能称为三个既有 seed 上的探索性计时证据。
- 预算削减的质量护栏不支持 1024：D 的 6 个 reduced/full 对照均超出 1pp ACC 下降护栏；2048 档 6 个对照中 5 个通过，唯一失败为 Dirichlet seed 404，下降 3.06pp。允许小幅下降不等于必须 ACC 提升，但 1024 档尤其 Dirichlet 不能描述为“小幅质量损失”。
- D/E 相比 B 有明显空间代价：在 full 档，隔离回放中的 D/E 持久方法数组约 26.08 MiB，B 约 0.73 MiB，增加 25.34 MiB；进程峰值工作集约 1.26–1.53 GiB。峰值只覆盖 CPU 独立训练回放，不代表显存、准备阶段峰值或多进程/部署峰值。

## 重算的 D 完整 head 流程结果

秒数是逐 seed 的 `B−D` 或 `E−D` 后取中位数，括号内为 D 较快的 seed 数/3。比值是逐 seed 的 D/reference 比值取中位数。head 包含初始化、私有阶段、关系生成/交换及 public 阶段。

| partition | private limit | D 对 B：中位省秒 / 比值 | D 对 E：中位省秒 / 比值 |
|---|---:|---:|---:|
| IID | 1024 | 24.07 / 0.723 (3/3) | -0.78 / 1.013 (0/3) |
| IID | 2048 | 20.98 / 0.780 (3/3) | 3.49 / 0.947 (3/3) |
| IID | full | 25.62 / 0.831 (3/3) | 2.82 / 0.979 (3/3) |
| Dirichlet α=0.1 | 1024 | 27.31 / 0.681 (3/3) | -1.58 / 1.025 (0/3) |
| Dirichlet α=0.1 | 2048 | 24.10 / 0.772 (3/3) | 2.26 / 0.972 (3/3) |
| Dirichlet α=0.1 | full | 22.76 / 0.849 (3/3) | 4.67 / 0.966 (3/3) |

包含共享准备成本 `with_shared_preparation_seconds` 后，绝对省秒与 head 相同，因为同 case 三方法使用同一 preparation 成本；比例被共同成本稀释。比如 D/B 1024 档：IID 比值从 0.723 变 0.837，Dirichlet 从 0.681 变 0.800。初始化自身仅约 0.003–0.007 秒，秒级收益不是初始化差异造成。

## 质量护栏（D，reduced 对同 partition/seed 的 full）

| limit | ACC 通过 | ACC 下降（6 个 seed/partition 值） |
|---:|---:|---|
| 1024 | 0/6 | IID：2.11、2.09、2.40pp；Dirichlet：27.46、27.35、25.36pp |
| 2048 | 5/6 | IID：0.3833、0.3267、0.4550pp（均为下降）；Dirichlet：3.06、-0.76、0.28pp |

负“下降”表示 reduced 的 ACC 更高。B/E/D 在同配置内的最终结果与头摘要一致，因此报告中相同 seed 的质量差在三方法行重复是预期，不是 18 个独立质量样本；有效的独立 seed 仍只有三个。质量护栏只比较全局平均 ACC；最差客户端/同客户端最小变化更差，如 IID seed 404 的 limit 2048 虽平均 ACC 通过，最差客户端 ACC 变化约 -0.69pp（见 `quality_guardrails.csv`），不能把平均护栏解释为公平性或逐客户端保证。

## 计时异常与表述边界

- 逐轮计时发现两处应标记的单点异常，均保留在原始统计中、未排除：Dirichlet seed 606、limit 1024 的 B 在第 150 轮 generation 用时 36.885789 秒，该轮远高于 B 此阶段逐轮中位数 0.219 秒；IID seed 505、limit 2048 的 E 在第 143 轮 public 用时 15.0309955 秒，高于该阶段逐轮中位数 0.181 秒。它们提示阶段总时长可能受单轮偶发事件影响，但现有证据不能确认原因，也不能确认可复现性。配对总计时与本文汇总均保留这些观测。
- 对 E，1024 档 D 三个 seed 都稍慢；不得概括为 D 在所有档位都快于 E。2048 档 D 对 E 中位 head 优势约 2.26–3.49 秒，幅度相对小。
- `with_shared_preparation_seconds` 把完整数据准备成本加到每个方法的总口径，不摊销且复用同一准备；它是明确的共同成本敏感性口径，不是独立冷启动实测。private_limit 只限制每轮头部 SGD，编码器和 C0 仍来自完整私有数据，因此不是“小私有数据集”实验。
- 报告说完整 head 是含初始化口径，字段与 README 口径一致。`paired_cost.csv` 将初始化独列，同时总 head 与含准备口径也存在；引用时优先使用 head 总量，不能把 phase 秒简单再加到 head 总量之上。
- 这是同机、B/E/D 共存且轮换执行的配对计时，评估/oracle/摘要不在阶段秒表内；不是端到端墙钟时间、并行联邦轮时延或独立新 seed 的性能确认。54 条轨迹并不等于 54 个独立性能重复。

## 内存与其他边界

- `memory_summary.csv` 共 18 个 full-private 隔离训练回放；CPU `process_peak_working_set_bytes` 范围 1,355,280,384–1,641,615,360 bytes（约 1,292.5–1,565.6 MiB）。B 持久方法数组 770,528 bytes（0.73 MiB）；E/D 27,347,744 bytes（26.08 MiB），多 26,577,216 bytes（25.34 MiB）。
- 持久数组排除共同特征/图、Python 对象、覆盖观察器和瞬时临时数组；进程峰值回放关闭评估/oracle并只做 full 档。因此两种数字不可互相替代，也不代表完整应用的最大驻留内存。
- `completed.json` 的验证计数（关系比较、候选成员比较及历史锚点配对）与结果哈希是来源证据；本审阅没有重新运行训练、重新执行全 oracle，也没有逐轮独立复算所有数组内容。它们支持“记录为通过”，不等同于本次独立重演。

## 文件依据

- `experiments/private_workload/results_full/completed.json`：case/trajectory/replay 数、mismatch 与文件哈希。
- `summary.csv`、`paired_cost.csv`：54 方法级汇总和 252 个配对成本记录；本文独立按 partition/case/seed 从原配对数据聚合。
- `quality_guardrails.csv`、`final_clients.csv`：逐 seed 平均与客户端质量变化。
- `memory_summary.csv`：18 个隔离内存回放。
- `experiments/private_workload/README.md`、`report.py`、`run.py`：设计、计时、质量计算及验证口径。



