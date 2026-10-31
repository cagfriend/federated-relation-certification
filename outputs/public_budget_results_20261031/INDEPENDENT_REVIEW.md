# Public-budget results: independent review

日期：2026-10-31  
范围：只读检查 `experiments/public_budget/results_full`、其报告/清单与 `outputs/public_budget_results_20261031/timing_delay_flags.csv`；未训练、未改源码或结果。本文按主线评估主贡献计算成本，ACC 只作为固定预算护栏（允许最多 1 个百分点下降）。机制/梯度实验不在本轮验收范围。

## 审核结论

**结构与配对完整性通过；计时结果可作已知 seed、同机 serial CPU 的配对探索证据，不足以作为稳定性能确认。** 按照现存产物，18 个 partition×seed×case 的 case（2 partition×3 seeds×3 配置）、54 条 B/E/D 轨迹和 18 份最大 M fixed8 隔离 memory replay 均有产物。计划覆盖 `m4096_full`（8 步）、`m16384_full`（32 步）、`m16384_fixed8`（8 步），iid 与 Dirichlet 0.1，各 seed 404/505/606。`completed.json` 声明 51 个文件哈希、零 mismatch、398,131,200 relation comparisons、530,841,600 candidate membership comparisons、3,600 个历史 anchor round-method pair；我独立重算 51 个登记文件 SHA-256，全部匹配。

完整性记录还声明 prepared groups 6、8 份汇总/报告文件重生成后逐字节一致、历史结果 86 个文件未变。完成清单中逐项记录了实验源码 hash 和运行环境身份；已有 `run.check_case`/`check_profile` 审核覆盖 case 身份、source/environment、轮数方法及 schedule、全图 oracle/partition audit、指标、跨方法目标/heads 与 memory replay digest/持久字节。这里通过的是**产物可复核与一致性**，不等于独立新随机种子或隔离进程的性能复现。

配置审阅与结果字段显示 fixed8 仅限制学生 public 更新步数；public steps 从 38,400 降到 9,600，teacher 关系生成、全图 exchange 与 audit 仍按全图运行。共享准备在配对成本口径中单独列示。目标摘要、每客户端收到目标摘要、schedule/step/endpoint 与 B/E/D 对账是适合本实验验收的关键不变量；历史 anchor 检查及 memory replay 检查也已纳入正式结果验证流程。

## D 相对 B/E：原始全轮读数（已由暂停调整口径替代）

逐 case/seed 配对的报表汇总与 `summary.csv`、`paired_cost.csv` 一致。最稳妥的主张是 D 的 generation 省时，不宜将其扩大成 D 在整个 head 流程对所有基线和配置都更快：

- D 相对 B：18/18 个 case×seed 的 generation 更快。最大 M fixed8 的 head 中位数比值：iid 0.8656、Dirichlet 0.8247；D/B 在两个 partition 的 fixed8 都是 3/3 head 配对更快。
- D 相对 E：generation 同样 18/18 更快，但 head 只有 11/18 配对更快。最大 M fixed8 的 head 中位数比值：iid 1.0132（1/3 更快，配对中位省时为负，D 比 E 慢约 1.84 s）；Dirichlet 0.9681（3/3 更快）。因此不能笼统声称 D 的端到端 head 优于 E。
- generation_fraction 确实有用来解释构成差异，但 fraction 变化不等同于节省秒数；主张应同时给出绝对 generation/head 秒数。共享准备计入后的口径与 head 口径已分别保存，避免把准备成本重复归功于单方法。

## 同 M fixed8 与 full：预算效果与 ACC 护栏

同 partition/seed/M 的 fixed8 对 full 配对结果中，6/6 个 ACC 都在 `fixed − full >= -0.01` 护栏内；IID ACC 差中位数约 -0.00032，Dirichlet 约 -0.00265，最差单个配对约 -0.00497。方向和范围符合“降低学生预算允许小幅 ACC 回落”的设定，不把质量提升当成必要条件。最差客户端 ACC 可出现更明显回落（现报告中最大约 -0.0179），所以该 ACC 护栏只约束报告定义的全局 ACC；不应据此宣称客户端尾部质量受同一阈值保护。

fixed/full 的预算收益是预算缩短的效果，不能归因于 D 认证/生成机制。此前全轮原始计时在两组 seed 404 出现 fixed 慢于 full 的表观反转；经用户确认暂停轮并按共同掩码排除后，反转消失。当前预算结论以暂停调整后的派生计时为准，原始轮测量仍保留。

## 两个手动暂停区间：原始逐轮记录

原始轮记录及 `timing_delay_flags.csv` 显示用户确认这两段长 public 区间来自手动暂停进程；pipeline 与分项加总仅差 2–3 微秒量级，排除摘要加总/残差错误。它们不作为方法运行时间或故障计入，以下派生计时统一使用共同轮掩码：

| 配对 | round / phase | public 时间 | 同 case-method phase 中位数 | 倍数 | 同轮 pipeline | pipeline 未分配残差 |
|---|---:|---:|---:|---:|---:|---:|
| Dirichlet 0.1, seed 404, fixed8, B | 100 / public | 569.6480 s | 0.1404 s | 4,057× | 570.3031 s | 0.000002 s |
| iid, seed 404, fixed8, E | 119 / public | 142.9151 s | 0.1547 s | 924× | 143.3585 s | 0.000003 s |

这两笔原始测量仍完整保留在正式 JSON 中，但暂停轮从相应 partition/seed 的三个 case、B/E/D 的计时总和中共同排除。质量、目标、schedule、training 与内存结果保持原始记录。此处理不以中位数替换暂停时段。

## 内存读数及边界

18 份固定预算最大 M 的单方法 replay 与主轨迹分开，时间不计入速度统计，并以最终 head digest 和 persistent array bytes 回放对账。报表显示 D 相对 E 的持久数组字节差为零；相对 B 多 26,577,216 bytes（约 25.35 MiB），这是交换 D 的计算优化时要披露的空间成本。过程峰值工作集并不支持“D 更省峰值内存”的说法：D/B 中位约增加 21.1%（约 272.8 MiB），D/E 约相同。该 memory profile 仅对应最大 M fixed8 的隔离回放，不能推广到 full 或其他硬件/进程环境。

## 验收与可信边界

- **完整性/可复核性：通过。** 文件 SHA、case/seed/方法数量、轨迹和 memory replay 数量，以及全图/历史校验计数与报告重生成一致性均有正式产物支持。
- **计算优化主张：有限通过。** 可报告 D 相对 B/E 的 generation 用时优势；D 相对 E 的整体 head 优势不成立为普遍结论。paired seconds 是这批已知 seed 上的描述性测量。
- **固定预算护栏：通过。** global ACC 6/6 满足最多 1pp 回落限制；预算效应独立于 D 机制归因。需同时保留客户端尾部变化。
- **暂停调整后的计时：可作已知 seed 的派生比较。** 手动暂停轮已按共同轮掩码排除；它们是用户确认的暂停时段，不计作算法时长或故障。结果仍是已知 seed 的同机配对计时，不构成 isolated-process / 新 seed 确认。

如需确认跨运行环境的绝对秒数，仍需另做隔离进程重复/新 seed；本审核不从暂停轮推断算法表现。

## 算术来源与独立复算边界（补充）

我另生成了 `independent_calculations.json`。当前成本输入直接来自 18 份原始 JSON 的逐轮 `round_records`，应用共同暂停掩码后重算；暂停调整前的全轮算术保存在 `independent_calculations_raw_all_rounds.json`。18 份内存输入直接取自原始 `memory_*.json` 的 `process_peak_working_set_bytes`。ACC 使用原始 B 的 `summary.final_metrics.mean.acc`，预算步数和其他轨迹/质量字段保留原值。每个 seed 先同配置配对，随后对三 seed 的比值与绝对秒差取中位数；胜出数按配对中 D/固定预算是否更快逐个计数。没有把 `audit.json`、汇总 CSV 或报告表当成计算输入。

本节 D/B/E 计算表保留的是全轮原始计时历史复算，现已由暂停调整口径替代；保留它们只为追溯此前算术，不能用于主结论。预算 ACC 护栏与最差客户端变化使用未变的原始质量数据，仍然有效。更新主结论和当前独立计算请见下方“暂停调整后复算”。

memory 重算得 D/B peak working set 中位比值 iid 1.21118、Dirichlet 1.21108（增加约 286 MB，即 272.7 MiB）；D/E 分别约 0.99983、1.00009。持久数组字节与 memory replay digest/来源身份的一致性由主审的正式 replay/check_profile 结果支持，不是本次算术复算单独证明的事项。

因此，本文暂停调整后的 D 相对 B/E 读数、固定/全预算成本与 ACC 差，以及 peak working set 比值属于我从原始产物独立复算；51 项 SHA-256、两暂停轮的 round/phase 数值亦由我直接检查。18 个 `check_case`/`check_profile` 的完整机器校验、8 份报表字节重生成一致、6 份 prepared cache 验证、全图比较/历史 anchor 计数及旧结果 86 文件未改，是主审执行并传递的正式审计证据；我没有重复运行这些重型校验。独立算术可以确认报告数字的计算来源，但不能替代上述来源身份、oracle、schedule、目标摘要或历史引用校验。


## 暂停调整后复算（当前计时主口径）

用户已确认两段长 public interval 是手动暂停进程。本复算不把暂停段纳入计时，也不把它们记为故障。共同掩码为：iid seed 404 排除 round 119；Dirichlet 0.1 seed 404 排除 round 100。每个受影响 partition/seed 的三个 case 和 B/E/D 都排除同一轮；其他 seed 保留完整 200 轮。未用 median 替换。计时按 raw `round_records` 重算：generation 为保留轮 `generation_seconds` 总和；head 为 initialization 加保留轮 `pipeline_seconds` 总和；C0+head 再加原始 common preparation 与 shared loading。原始训练轨迹、质量/目标/schedule 检查、memory replay、51 个 hash 文件均未改。

详细逐 seed/case/method 算术在 `independent_calculations.json`；此前全部轮次算法原件保留于 `independent_calculations_raw_all_rounds.json`。暂停调整后的最大 M fixed8 配对中位结果：

| partition | 比较 | generation D/基线中位比 | generation 中位省秒 | head D/基线中位比 | head 中位省秒 | head 胜出 |
|---|---|---:|---:|---:|---:|---:|
| iid | D/B | 0.3306 | 26.67 | 0.8656 | 21.86 | 3/3 |
| iid | D/E | 0.8044 | 2.97 | 1.0132 | -1.84 | 1/3 |
| Dirichlet 0.1 | D/B | 0.4237 | 17.79 | 0.8488 | 19.17 | 3/3 |
| Dirichlet 0.1 | D/E | 0.7809 | 3.78 | 0.9681 | 3.22 | 3/3 |

同 M 的 B fixed/full head 比值（seed 404/505/606）：iid 为 0.6959/0.6383/0.6152，Dirichlet 0.1 为 0.6212/0.6053/0.6222；C0+head 比值依次为 iid 0.7561/0.7021/0.7179、Dirichlet 0.7207/0.6862/0.7349。六组 public optimizer steps 均为 full 的 0.25 倍。ACC 及 memory 未受暂停口径影响：6/6 ACC delta >= -0.01；峰值内存 D/B iid 1.2112、Dirichlet 1.2111，D/E 约 1.0。

这次暂停调整修正了 seed 404 的预算 wall-time 比较；它没有改变已记录的质量或计算轨迹。固定预算效果仍只归因于学生 public SGD 预算缩短，不归因于 D 机制。读数是对本批已知 seed、同机串行测量的暂停调整派生比较，不是新 seed/隔离进程性能确认。
