# Demand 四方法计时定向补测

复用完成的按需对照、训练快照、样本、200 轮预算与消息协议。在 M=4096 的三个受供电状态影响的块上按原顺序重测四条路径。

| 划分 | 原配对块 | 补测顺序 |
|---|---:|---|
| 2021 强非 IID | 1 | Demand → D → E → B |
| 2021 强非 IID | 2 | B → Demand → D → E |
| 2021 IID | 2 | E → D → Demand → B |

预计 12 次独立单线程完整训练。逐轮核对原审计的教师关系、头参数和学生实际目标，并检查 Demand 的边范围及逐类消息字节。三组原本有效的块继续用于合并分析。

整个补测块满足原插电与休眠判据才可采用。若首轮尝试未通过，最多按原顺序再试一次。按执行顺序采用首个有效补测，耗时与结果好坏不参与选取。程序再次启动时已封存的整块复用，未封存的四条路径从头按顺序重测。新目录保留所有补测尝试和合并表，原始结果目录与原始报表可随时对读。

每个划分最终需三个有效块才能出正式判定。完整头部平均省时至少 3%、且在三个配对块中至少赢两次，沿用原实验门槛。通信和原生聚类质量的等价性按各路径原有审计口径检查。

## 运行

同一机器插电后在工作区根目录启动。

```powershell
D:\anaconda\python.exe -B -m snapshot_routing.on_demand.retest.run --preset full
```

原始结果默认位于 `outputs/snapshot_routing_on_demand_full`，补测写入 `outputs/snapshot_routing_on_demand_retest_full`。中断后在原命令末尾加 `--resume`。可通过 `--source`、`--confirmation`、`--output` 指定目录。

`replacements.csv` 对照原始与补测的逐路径秒数和供电记录。`report.md` 和 `comparisons.csv` 汇总有效块，`runs.csv` 和 `paired_blocks.csv` 保留全计口径和实际纳入标记。`--preset smoke` 重跑一个合成四方法块验证补测流程。
