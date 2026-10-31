# 开发验证记录（云端，2026-10-31）

本包在推送前已在云端 Linux 机器完成单元测试与官方 smoke 全流程；正式 `full` 实验未在此运行，由用户在本地执行。

## 环境

- 4 核 CPU、无 GPU，Python 3.12，torch 2.15.0+cpu，numpy 2.5.4，scipy 1.18.1，scikit-learn 1.9.1（独立 venv，与仓库运行时一致性检查兼容：检查只要求同一运行内冻结一致）。
- 源码基线：仓库 commit `1e37ed4` 的 `public_scaling` / `noniid_clustering` / `public_budget` 未作任何改动，本包为新增目录。

## 单元测试

命令：

```bash
python -W error::ResourceWarning -m unittest experiments.private_workload.test_workload -v
```

结果：6 个测试全部通过。覆盖：正式/smoke 计划冻结与档位校验、抽样子流 403 的确定性与独立重算、全量档与 `public_budget` 引擎逐轮头摘要/traffic/私有损失一致、限量档子集样本量/摘要/直方图/步数/端点记账、全图 oracle 计数与单方法回放一致、报表配对/逐方法护栏/workload effects。

## Smoke

命令：

```bash
python -m experiments.private_workload.run --preset smoke --memory-audit --download
```

结果（`completed.json`）：18 组全部完成，54 条训练轨迹，18 条隔离内存回放，`mismatches=0`，关系比较 20736 次，候选成员比较 27648 次。逐 case 经 `check_case` 独立重算校验（含私有子集日程重算）后落盘；`report.md`、`paired_cost.csv`、`workload_effects.csv`、`quality_guardrails.csv`、`memory_summary.csv` 均生成。

抽查（iid seed404）：priv64 每轮每客户端实际样本 [64, 64]、伪标签直方图和等于 64；privfull 为 [448, 448]。smoke 私有 batch 为 128，故 priv128 与 priv64 步数同为每轮 2 步，属 smoke 档位 artifact，不影响正式档（batch128 下 full/2048/1024 分别约 57/16/8 步每客户端每轮）。

smoke 原始结果目录含云端绝对路径，未随代码入库；正式运行请在本地按 README 命令生成 `results_full`。
