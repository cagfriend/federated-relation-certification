# 本地后续材料与发布状态

盘点日期2026-11-09；远端基线`46b25e333228`未包含`lr_compute`和`lr_repeat`执行包。本次随附的是不可作为运行入口的文档/审计快照，不复制原始运行JSON或缓存。原文件相对链接在快照位置不一定成立，按下方来源映射定位。

## P1：已完成并已审核，但原执行包尚未发布

8配置×B/E/D共24次200轮运行，加6次隔离内存回放。关系比较353,894,400次、候选成员比较471,859,200次，零错误；同配置轨迹与原0.05锚点一致。

D/B完整头部8/8更快，省23.55%–48.96%；D/E为7/8更快，K64/IID/1101慢0.33%。质量是原0.05轨迹复现，不新增独立随机实例。隔离内存只测两个配置，D/E较B占用更多；K64/强非IID/1002含准备总成本继续标NA，保留方法计时。每方法仅一次，探索性解释，不替代重复确认。

## P2：已有实现，正式完成状态单独判断

本次本地只读盘点：`completed.json`存在=False，`runs/*.json`数量=6。缺完整封印、正式报告及结果审核时，不称为完成，也不把开发smoke当性能证据。本次不启动、不恢复该实验。

## 快照清单

|本地原始路径|本次保存路径|SHA256|
|---|---|---|
|`experiments/lr_compute/results_full/report.md`|[docs/history/local_followups/experiments/lr_compute/results_full/report.md](../../docs/history/local_followups/experiments/lr_compute/results_full/report.md)|`007de319bde553732141268dcd277be4b9467b0292f6b218983c9eee6d2cecf7`|
|`outputs/lr_compute_results_20261106/REVIEW.md`|[docs/history/local_followups/outputs/lr_compute_results_20261106/REVIEW.md](../../docs/history/local_followups/outputs/lr_compute_results_20261106/REVIEW.md)|`7df3cd16b47b58abe4c33504dc97aac6ec703d002e8cf43c8f75b54cb6eb5b5c`|
|`outputs/lr_compute_results_20261106/audit.json`|[docs/history/local_followups/outputs/lr_compute_results_20261106/audit.json](../../docs/history/local_followups/outputs/lr_compute_results_20261106/audit.json)|`04a68884b8eed0ccbd11d4b5ae7655f73071868f2ba19f958fc178f0aa9eb4e9`|
|`experiments/lr_compute/PREREGISTRATION.md`|[docs/history/local_followups/experiments/lr_compute/PREREGISTRATION.md](../../docs/history/local_followups/experiments/lr_compute/PREREGISTRATION.md)|`bc32d94d68b540e872af9136526d03844f619c7521e8d802c55b2f52e0917b76`|
|`experiments/lr_repeat/PREREGISTRATION.md`|[docs/history/local_followups/experiments/lr_repeat/PREREGISTRATION.md](../../docs/history/local_followups/experiments/lr_repeat/PREREGISTRATION.md)|`50290a5e5f24c711b507f22d14c1b85b50045ce1643228c39e2f3247561152b6`|
|`experiments/lr_repeat/VALIDATION.md`|[docs/history/local_followups/experiments/lr_repeat/VALIDATION.md](../../docs/history/local_followups/experiments/lr_repeat/VALIDATION.md)|`e63816312ad889ee5ade86d7d66e5306c232a624281525f541060e4f10682253`|
