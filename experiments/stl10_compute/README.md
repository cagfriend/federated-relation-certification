# STL-10 固定 2 步 B/E/D 计算对照

按 `PREREGISTRATION.md`（冻结版）执行：公共 2 步（长程验证按预先规则
选定）、M16384、200 轮、完整私有更新，IID/Dirichlet α=0.1 ×
seed1001/1002/1003 × B/E/D，共 18 次独立进程运行。先验精确性
（逐轮审计零错误、三元组轨迹一致、双锚点），再报同批次内 D/B、
D/E 完整头部净省时与生成解释，以及内存/端点/通信/退化护栏。
每方法只跑一次，计时为探索性，不作独立确认判定。

## 运行

正式运行（需要 `experiments/stl10_transfer/results_full` 与
`experiments/stl10_longrun/results_full` 作锚源；开始与每次恢复都
要求 ACLineStatus=1）：

```
python -m experiments.stl10_compute.run --preset full
python -m experiments.stl10_compute.run --preset full --resume   # 中断后续跑
```

smoke（合成夹具，2 划分 × 3 方法 = 6 条短运行，只验证实现）：

```
python -m experiments.stl10_compute.run --preset smoke --source-results experiments/stl10_transfer/results_smoke_final
python -m unittest experiments.stl10_compute.test_run
```

输出：`results_<preset>/` 下 18 条封签运行 JSON、runs.csv、
paired_cost.csv、paired_summary.csv、guardrail.csv、summary.json
与 report.md。
