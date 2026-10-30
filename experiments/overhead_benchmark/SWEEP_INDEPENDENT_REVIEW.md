# 独立审阅：更新幅度扫描实现

审阅日期：2026-10-28  
范围：`experiments/overhead_benchmark` 的 certification、sweep runner、配对统计、README、测试与旧结果保护。按委托要求未启用 skill、未改产品源码、未运行完整计时扫描。

## 结论

| 项目 | 结论 | 依据 |
|---|---|---|
| 方法忠实性与比较公平性 | 通过 | sweep 固定 B/E/D，三者共用固定特征、匹配图和参数轨迹；逐轮轮换执行顺序。E 的 point 分支只判断逐点 singleton，并刷新模糊样本，不创建关系位集或执行关系交集检查。 |
| 跨幅度配对与缓存独立 | 通过 | Fixture 以同种子和独立 RNG 序列生成起点与标准正态更新，再由 scale 缩放；每个幅度由独立 `run_case` 新建 Fixture/Engine/cache。作业顺序 RNG 与特征/更新 RNG 分离。 |
| 统计口径、初始化与比值方向 | 通过 | per-case 汇总含 `with_initialization_measured_seconds`；跨种子先按同种子算 D/reference，再汇总中位数/范围，方向明确为 D 除以 B/E，<1 表示 D 成本较低。摘要另报含初始化生成成本。 |
| 参数、文件名和结果保护 | 通过 | 默认参数符合委托配置；scale 有限、非负、唯一校验；float repr 编码进文件名；非空输出目录拒绝写入。旧结果保护清单 24 项全部 SHA256 匹配。 |
| 旧入口兼容及审计 oracle 复用 | 通过 | main/boundary/all 默认入口保留；A/B/C/D 原定义保持不变，`METHODS` 新增 E；protocol/codec 未改。audit 只计算一份外部 oracle labels供成员性校验复用，未传入 Engine，仍在计时外。 |

## 关键实现核对

- `certification.py:135-153`：point 分支使用 `candidate_matrix()` 与每行候选数；仅 singleton 两端计为认证关系，其余样本重算。它不调用 `candidate_sets()`，也不承担 relation 分支的 bitset/intersection/edge-resolution 开销。`candidate_entries` 现由已得 `sizes.sum()` 复用。
- `certification.py:154-180`：D 的 relation 分支仍使用候选 bitset；先认证候选集合不交或相同 singleton，剩余边端点去重后仅重算非 singleton 点。
- `run.py:184-222`：独立全量 oracle 在 `audit()` 中生成；保存一次 `oracle_labels`，仅用于验证候选集合是否包含真赢家。验证计时单独累计，不进入方法 generation/exchange 计时。
- `run.py:226-263`：sweep 默认方法为 B/E/D；同一 case 共享 Fixture 快照，初始化及每轮均轮换方法次序，初始化计入汇总。幅度更新由 fixture 外部预先规定，符合方法简述中的“固定快照、指定扰动”边界，不声称在训练模型。
- `run.py:427-450`：同种子各幅度排列随机化；同一幅度唯一性检查；scale token 使用浮点 round-trip 表示；非空目录保护。
- `run.py:454-495`：拒绝未验证结果、重复 seed/scale、错误方法集合；输出配对成本比和胜出数。无把“方法耗时中位数之比”误作配对比值。
- `run.py:504-579`：legacy suite 选择、默认维度/样本/类别/轮数/种子及 memory worker 的 scale 透传均保留。
- 对照 `outputs/联邦聚类方法简述_20261022.txt`：交换对象仍为硬关系和计数协议；认证优化仍只减少硬关系生成阶段前向，未将训练/蒸馏带梯度前向纳入该算法假设。

## 实际验证

- `python -m unittest experiments.overhead_benchmark.test_benchmark -v`：19 项全部通过（0.545 秒）。覆盖 point/relation 认证反例、缓存独立与累计、同种子跨档轨迹、文件名唯一、输出目录拒绝覆盖、配对 ratio 算法与旧场景不变量。
- `python -m experiments.overhead_benchmark.run --help`：通过；显示原 suite 入口和 sweep/scales 参数。
- 独立读取 `result_preservation_20261028.json` 并重算清单 SHA256：检查 24 个旧结果文件，0 个不匹配。
- 未执行完整计时；也未另跑 smoke，因为现有 19 项已含隔离 sweep 小例，且不需要再产出文件。

## 未覆盖范围 / 有条件说明

- 本审阅不验证完整 200 轮、6 档的实际耗时、机器负载稳定性或 memory-audit 子进程运行；这些应由主代理在独立空目录中完成。
- 参数解析允许用户覆盖样本、维度、轮数和种子，因此“指定 4096/6客户端/200轮/三种子”由默认值而非不可变硬编码保证；默认值与批准协议一致。
- 结果目录保护针对非空目录；已存在但为空的目录可以复用，这是安全的，因为无旧结果可覆盖。
- 数值边界使用现有 `1e-10` 实用 guard，不是 IEEE 形式化误差证明；文档与代码已明确这一限制。

## 续跑脚本静态审阅（2026-10-28）

范围：`work/continue_overhead_sweep.py` 静态阅读；未运行脚本、测试或计时验证。

| 项目 | 结论 | 依据 |
|---|---|---|
| 产品源码一致性 | 通过 | 脚本逐项读取 `source_hashes.json`，拒绝路径名异常或哈希变化后才导入当前 runner。 |
| 已完成案例与旧数据保护 | 通过（按现有计划） | 只接受计划中的案例文件；每个已存在案例核对场景/scale/seed、完整 config、B/E/D、启用校验、0 mismatch 及每种方法的 round 0..rounds 记录；新案例用独占模式 `open("x")` 创建，已有案例不会被覆盖。 |
| 配对与汇总更新 | 通过 | 所有计划任务有唯一文件名；逐次只跑 `missing[0]`，完成后从磁盘案例重建 `summary.csv`；全计划完成才更新 sweep 汇总。新增断言确认计划恰为六档 scale × seed 101/202/303，计划范围与批准配置相同。 |
| 计划完整性 | 通过 | 新增断言要求默认 `Config()`，且 `job_plan` 长度与 `(scenario, scale, seed)` 集合精确匹配 sweep × `SWEEP_SCALES` × (101, 202, 303)。这些检查位于读取/写入案例结果之前；不完整或改写的计划会拒绝续跑。 |

其他保护核对：计划中额外案例文件会被拒绝；每次最多运行一个缺失配置；BLAS 预热和 runner thread limit 与原入口一致；输出摘要文件会按已验证案例重建写入，案例数据文件采用独占创建。未检查或验证实际续跑结果。以上结论是静态复核，不代表执行过新增断言。

## 幅度细化续跑编排静态审阅（2026-10-28）

范围：`work/continue_overhead_sweep.py --refine` 分支；未运行脚本、测试或性能扫描。

| 项目 | 结论 | 依据 |
|---|---|---|
| 细化参数与结果隔离 | 通过 | `--refine` 固定 scale 为 0.10/0.12/0.16、seed 为 101/202/303、默认 Config，并使用独立 `results_sweep_refine`；严格核验9个唯一组合。案例仍从 `run_case` 生成，每次仅补一个缺失 case 且以 `open("x")` 创建。 |
| 来源源码与核心运行时 | 通过 | 初始化时复核 coarse 记录的核心源码 hash、Python 与 NumPy 版本；每次调用都再核对当前 Python/NumPy 及产品源码 hash。refine 分支每次核对 `refinement_origin.resolve()` 与预期 coarse 目录一致。 |
| 新目录初始化中断恢复 | 通过（损坏元数据安全失败） | 新目录仅接受不存在或只含 `source_hashes.json` 的目录。先独占创建并写入源码哈希，再独占写入 environment 标记；若中断后留下完整且匹配的 hash 文件，重试可继续写 environment。若 hash JSON 截断或与来源不匹配会拒绝，不覆盖、不尝试修复。environment 文件本身若写入时中断则安全报错，需人工处置。 |

复核后此前记录的运行时漂移与“hash 尚未完整写完”恢复风险已消除；损坏元数据仍会安全失败。未发现细化配置会写入粗扫描目录。细化摘要仍从细化目录的已验证 case 重建。未核验 coarse 原始逐案例数值及细化脚本实际运行结果。
