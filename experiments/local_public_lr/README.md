# 单配置局部公共学习率实验

只在 strong / IID / seed1001 上比较两条200轮B轨迹：全体公共LR0.05，以及仅100张客户端0/3降至0.0125。其余客户端仍0.05，公共仍两步。新增完整观测基线，让160–200轮也有真实T0/T1/T2记录。

本实验检查局部干预能否解除严重退化及每段更新的变化，不比较认证省时，不要求ACC提高。完整冻结设计见 [PREREGISTRATION.md](PREREGISTRATION.md)。既有实验源码、结果和缓存保持原样。

## 本地正式运行

插电后在项目根目录运行（代码交付时未启动正式实验）：

```powershell
Set-Location 'C:\Users\tjp\Documents\Codex\2026-10-14\new-chat'
D:\anaconda\python.exe -m experiments.local_public_lr.run --preset full
```

中断后使用同一入口加 `--resume`。默认输出 `experiments/local_public_lr/results_full/`。已经完成的单次轨迹会核验后保留；未完成的整条轨迹重跑，不在半轮恢复。看到 `Finished` 和 `finished.json` 才算两条均完成。

默认复用 `quantity_heterogeneity/results_full` 的缓存及原200轮B记录；并核验 `low_capacity_diagnostic/results_full` 的全局低LR/private-only历史参照。无需重新下载或预训练。环境、源码、缓存、参照文件不一致时停止。可通过 `--source-results` / `--diagnostic-results` 指定同协议完整结果目录；路径和摘要在首次运行时冻结。

## 执行顺序与输出

1. 核验两个历史实验的源码/环境、完成清单、输入与参照身份。
2. 全体0.05基线跑200轮，并逐轮匹配历史非计时字段与测试评估。失败立即停止，不开局部干预。
3. 同初始状态跑局部降LR，原样记录所有检查点和集中事件。
4. 按160/180/200每个客户端逐点判断：占用簇>1且最大簇<99%。缺失失败，分别展示两个100张客户端与其他4个。通过只表示解除严重退化。

`runs/*.json` 保存原始记录；`environment.json` 冻结计划/源码/运行环境/输入/参照；电源日志单列。`report.md` 与 `summary.json` 给出判定，`late_comparison.csv` 展示所有晚期客户端。`stages.csv`、`losses_and_deltas.csv`、`stage_effects.csv`、`stage_contrasts.csv` 保存观测与相对完整基线的差值，`client_rates.csv` 给出各客户端实际公共权重/有效LR。历史全局低LR/private-only仅作同口径参照。

两个分支共享主Spec `public_weight=0.5`；逐客户端向量另外冻结，实际调用公共SGD时仅替换该客户端Spec。私有SGD仍为原LR0.1。局部改动也会影响后续教师反馈，因此仍不能把恢复归为唯一机制，也不能从单个IID配置推广到非IID。

## 开发验证

```powershell
D:\anaconda\python.exe -m unittest experiments.local_public_lr.test_local_public_lr -v
D:\anaconda\python.exe -m experiments.local_public_lr.run --preset smoke --output outputs/local_public_lr_smoke --cache outputs/local_public_lr_fixture_cache
```

smoke是两条各3轮的合成小数据，不构成科研结果。开发验证及独立复审见 `VALIDATION.md`（交付时补齐）。
