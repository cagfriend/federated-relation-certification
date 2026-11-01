# STL-10 公共步数候选长程验证

按 `PREREGISTRATION.md`（冻结版）执行：只跑 B 方法，公共步数 1/2 步
两档 × seed 1002/1003 × IID/Dirichlet α=0.1，M16384，200 轮，共 8 条
长程轨迹，机械判定 S1/S2/Q1/Q2 并按冻结规则选档。本实验不产出认证
省时结论；通过仅指对应档位的 4 条轨迹满足约定操作标准。

## 运行

正式运行（需要 `experiments/stl10_transfer/results_full` 的环境、
准备缓存标记与历史 8 步 B 运行作锚；开始与每次恢复都要求
ACLineStatus=1）：

```
python -m experiments.stl10_longrun.run --preset full
python -m experiments.stl10_longrun.run --preset full --resume   # 中断后续跑
```

smoke（合成 STL-10 夹具，自备准备缓存，12 轮，只验证实现与判定
机械流程）：

```
python -m experiments.stl10_longrun.run --preset smoke
python -m unittest experiments.stl10_longrun.test_design
```

输出：`results_<preset>/` 下每条轨迹一个封签 JSON，另加
`report.md` 与 `verdict.json`（档位判定与选档结果）。
