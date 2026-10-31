# Public-budget 独立代码复审

日期：2026-10-31  
范围：只读审查 `experiments/public_budget/{design,student,engine,run,report,test_budget}.py`；未修改实验源码或结果。允许运行并已运行 7 项小型单元测试；未启动正式训练、数据下载或 smoke 训练。

## 结论

整体设计符合本次计算优化主线：三种 case 是小 M full、最大 M full、最大 M fixed 8 steps；覆盖 IID / Dirichlet 0.1、seed 404/505/606 和 B/E/D。teacher 关系生成、完整关系交换及 audit 都仍作用于全图；fixed 只截断学生 public SGD 的原 seed 402 随机边序前缀。首轮 bootstrap、后续 teacher 快照漂移及计时边界沿用 public_scaling core。报告的质量护栏方向正确，固定预算允许 ACC 下降最多 0.01，且声明不要求协作质量提升，也不声称独立 seed/process 性能确认。

## 需主 AI 关注

- **低风险验证缺口：旧 core anchor 没有显式比较持久数组字节。** `run.py:45-50` 的 `check_reference()` 对历史 full anchor 检查逐轮 head digest、traffic、public steps、forward endpoints 和完整 metrics，但没有比较已有的 `persistent_method_array_bytes`。`check_case()` 也只把 summary 的 bytes 与新 case 最后一轮记录对账，不会把每个方法的 bytes 与历史 core 结果核对。新旧实现复用 `Method` 和生成器，代码上预计相同，但“同配置旧 core bytes 严格一致”目前没有运行期断言。若把该要求解释为需要机器可检验证据，建议补上 per-method/per-round 对账。
- **目标一致性没有单独留存/对比证据。** 现有路径每个方法都通过 core `audit()` 检查自己的 teacher 关系、解码和目标向量，且跨方法头轨迹、traffic 与 metrics 比较严格；由此在同快照下可推导目标相同。不过结果没有 target digest/目标向量逐方法比较，也没有直接 cross-method 检查。历史 anchor 也没比较 `public_loss`。这不表明发现了目标漂移，属于对“目标严格一致”的证据表达不足。
- 报告在不完整合成输入下可能出现 ACC 已有值而 NMI/ARI 缺失时仍显示 `within_acc_guardrail=true/false`，同时 status 为 `pending_incomplete_metrics`。正式 runner 会要求完整最终指标，当前正式路径不会产生此组合；展示层轻微不一致。

## 已核对的实现细节

- `design.py` 的 formal plan 生成 `(4096, full, 8)`、`(16384, full, 32)`、`(16384, fixed, 8)`，共每 partition/seed 3 case；18 cases、54 条 B/E/D trajectories。三 case 的 preparation 配置相同。
- `student.py` 以 `[seed,402,client,round,0]` 生成原始全图边排列；fixed 精确取前 `steps * public_edge_batch` 条。coverage observer 仅记录实际被学生消费的边及其端点，并在方法计时和持久数组测量之外。
- `engine.py` 先完成每个客户端全图教师关系，再通过完整 `protocol.exchange()` 构造每个学生自己的收到目标，最后仅由 `update()` 应用 fixed 公共 SGD。历史 generator snapshot 没被学生更新覆盖，下一轮变化依旧相对上次 teacher 快照。
- pipeline stopwatch 在每轮诊断行组装前结束，audit/coverage 与 evaluation 使用外层计时并记录为 excluded；初始化被计入 head pipeline，shared preparation + shared loading 被单独加总。
- `run.py` 保存冻结 source/runtime/plan identity；resume 对已有 case 做完整 payload、身份、round/method 覆盖、schedule、coverage、metrics、时间汇总和 oracle 覆盖检查。18-case 完整性由固定的 seeds × partitions × plan 遍历保证。
- 可选 memory audit 在独立子进程、单方法、无 validate/metrics replay 中测 process peak，且只在固定最大 M case；replay 用最终 head digest 和 persistent array bytes 对账 paired 结果，耗时不纳入速度比较。
- `report.py` 的 ACC delta 为 fixed − same-M full 的 B，护栏判定 `delta >= -0.01`；paired cost 先在 partition/case/seed 内比较，再按 seed 汇总。文本明确指出不做独立新 seed/process 速度确认。

## 验证

运行 `python -m unittest experiments.public_budget.test_budget -v`：7/7 通过（约 1 秒）。覆盖 formal plan、full epoch 等价、full B/E/D 轨迹等价、fixed 独立手算 SGD、全图 oracle 与覆盖、单方法 memory replay 的 digest/bytes、历史引用重复记录拒绝。

## 主 AI 更新后的复核（2026-10-31）

主 AI 已落实前述证据缺口，我复读了更新后的 `engine.py`、`run.py`、`report.py` 和 `test_budget.py`：

- 每轮结果新增 committed aggregate count digest 和每客户端 received-count digest；`check_case()` 要求同一轮 B/E/D 的 heads、schedule、steps、student endpoints、committed target digest、private loss、public loss 一致，并验证每个 student 收到的目标摘要与 committed aggregate 一致。
- 历史 full anchor 对账新增 `public_loss` 与 `persistent_method_array_bytes`。本复审先前列出的“目标/字节未显式核验”问题已解决。
- 报表现有 `budget_effects.csv` 分列 fixed 相对同 M full 的成本/steps 变化，并说明预算变化不能归因于 D 认证机制；ACC 护栏使用 fixed−full 的正确方向及 1e-12 浮点容差。最差客户端 ACC 差与同客户端最小 ACC 差分别报告。
- 已按要求复跑当前小单测：8/8 通过（约 1.1 秒）。测试触发 4 个 `ResourceWarning`，因为 `test_budget.py` 读 CSV 后未关闭文件；测试结果仍通过，不涉及实验源码/结果正确性。

尚有一个仅影响不完整输入展示的一致性细节：当 ACC 存在、但 NMI 或 ARI 缺失时，`within_acc_guardrail` 仍会返回布尔值，同时 `status` 是 `pending_incomplete_metrics`；报告文案称缺少必要指标时为 pending。正式 `check_case()` 要求指标完整，常规完整结果不会触发。其余审查结论维持。


## Primary-agent final acceptance

Two GPT-6 Luna/high subagents were used. The report subagent implemented report.py and manually verified paired costs, allowed ACC decline, full/fixed budget effects and partial-input handling; the primary agent inspected the implementation and added an automated hand-calculated boundary test. The independent reviewer checked the complete teacher graph, student sampling, teacher snapshot drift, timing, preparation cost, resume and memory scope, and ran eight fixture tests. The primary agent implemented and verified the requested explicit received/committed target digests and historical anchor loss/persistent-byte checks. The CSV file-handle warnings in the review were fixed before final source freeze; the final eight tests also passed with ResourceWarning promoted to error. The partial-input ACC/status display nuance remains nonblocking: formal cases require complete metrics and quality tables explicitly carry status; it does not affect valid formal inputs.

Final official reduced smoke: 18 cases / 54 trajectories / 18 isolated single-method memory replays; 15,552 full-graph relation checks and 20,736 candidate checks, zero mismatches. Fifty-four historical anchor round-method pairs matched. Resume preserved all 18 cases and reused 18 profiles. The primary audit verified 51 output hashes, regenerated eight reports byte-identically, and rejected 54 re-sealed budget/received-target/coverage corruptions. Eighteen formal configurations and six existing full cache groups passed read-only preflight. Eighty-six prior non-IID/mechanism result files and all frozen core/preparation sources remained unchanged. An initial development smoke was archived after expected source-freeze rejection during report edits; it is not the accepted smoke evidence.

Accept implementation for stage-1 cost exploration with the registered one-percentage-point quality guardrail. No formal performance or quality conclusion is drawn yet. No new-seed performance confirmation, real network timing, new compression or private-workload reduction is claimed.
