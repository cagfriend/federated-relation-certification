# E38 快照协议：B/E/D 正确性回放与计时

按 [实验设计](../../docs/E38_CERTIFICATION_TIMING_PLAN.md) 执行。B 全量生成，E 逐样本认证，D 关系认证。中心头、0.5 全程保护、全客户端私有频数校正及公共两步完全相同。默认读取本地 E38 历史结果和准备缓存，不覆盖原结果。

从实验工作区根目录运行：

```powershell
D:\anaconda\python.exe -B -m experiments.snapshot_certification_timing.run --preset full
```

默认先做 12 条 × 200 轮的非计时审计，全部通过后再做 36 次 × 200 轮独立进程计时。也可先加 `--stage audit` 单独对齐，之后用同一输出目录及 `--stage timing --resume` 开始计时。普通中断原命令加 `--resume`；已校验和封存的完整进程保留，未完成的进程重跑。若正式计时期间有可确认的休眠、暂停或计时中断，原运行全部完成后，用 `--resume --rerun-block 1201_iid:2 --reason "已确认休眠"` 补跑同一三方法块；结果和原块对照保存在 `reruns/`，原结果及主报表不自动替换。

`--history` 接受带回执的 E38 结果目录。`--cache` 接受含各 seed 文件夹的缓存根；默认是历史目录的 `cache`。若缺缓存，可另给 `--data-dir` 尝试重建；重建必须通过与 E38 相同的输入摘要和模型身份检查。若重建和原归档的文件摘要不同，需要找回原缓存或另行核验，不能从本实验静默绕过。准备阶段在本机复测 AE 与确有发生的快照筛选/回放，计入含准备口径；正式进程从同一份校验过的快照开始。

查看 [实验设计](../../docs/E38_CERTIFICATION_TIMING_PLAN.md) 中的判定口径。输出目录默认 `results_full`；`report.md` 为汇总，`comparisons.csv` 和 `paired_blocks.csv` 给出两个基线的配对结果，`quality.csv` 与 `round_metrics.csv` 包含质量和计算机制指标，原始轨迹在 `audit/` 和 `timing/`。进程历史峰值与持久认证缓存分别报告。Windows/Linux 休眠估计和可读电源端点仅作为审核提示。

合成短测可用 `--preset smoke`。此模式每方法两轮，公共图只有一个完整学生批次，仅用于路径与校验，不用于性能结论。
