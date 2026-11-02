# STL-10 固定 2 步重复计时确认

按 `PREREGISTRATION.md`（冻结版）执行：与 `stl10_compute` 探索批次
完全相同的配置（公共 2 步、M16384、200 轮、完整私有更新），
两划分 × seed1001/1002/1003 × B/E/D × 3 次技术重复 = 54 次独立
进程运行。先在 seed 内对重复取均值再配对，按 C1/C2/C3 逐划分机械
判定 D/B、D/E 省时是否获得重复确认；本批次计时不与探索批次混合，
探索批次只作轨迹锚点。

## 运行

正式运行（需要 transfer、longrun、compute 三处 results_full 作锚源；
开始与每次恢复都要求 ACLineStatus=1；预计墙钟约 2–3.5 小时）：

```
python -m experiments.stl10_repeat_confirmation.run --preset full
python -m experiments.stl10_repeat_confirmation.run --preset full --resume
```

smoke（合成夹具，18 条短运行，只验证实现与判定机械流程）：

```
python -m experiments.stl10_repeat_confirmation.run --preset smoke
python -m unittest experiments.stl10_repeat_confirmation.test_run
```

输出：`results_<preset>/` 下 54 条封签运行 JSON、noise.csv、
seed_pairs.csv、guardrail.csv、verdict.json 与 report.md。
