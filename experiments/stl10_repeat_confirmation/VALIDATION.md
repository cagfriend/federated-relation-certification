# 云端验证记录（2026-11-02，推送前）

- 单元测试：`python -m unittest experiments.stl10_repeat_confirmation.test_run`
  9 项全过。覆盖：54 条正式矩阵与顺序平衡（每块每方法恰好居首
  一次）；C1/C2/C3 判定（通过与 D/E 失败分支）；块内一致性；
  **锚点回归**——缺失 compute 锚点必须硬失败、锚定 seed 缺失
  longrun 锚点必须硬失败、篡改轨迹或篡改锚点必须被拒绝（针对
  stl10_compute 首版锚点静默跳过 bug 的同类问题）。
- Smoke：`--preset smoke` 完成 18 条独立进程运行（seed1001 ×
  两划分 × B/E/D × 3 重复，夹具 M128、3 轮）。块内 9 条记录
  非计时字段一致性、oracle 覆盖计数与 mismatches=0、判定与噪声
  汇总、报告生成均通过；`--resume` 保留全部并复验一致。夹具
  计时无意义（D 在微型合成数据上更慢），只验证机械流程。
- 正式 preset 的三重锚点与 ACLineStatus=1 门槛依赖用户本地三处
  results_full，云端未跑正式矩阵。实现基线为探索批次实际执行
  的修复版 `stl10_compute`（已从 GitHub 拉取核对，含
  verify_triples 与 LOCAL_FIX.patch 的全部修复）。


## 2026-11-02本地校验补充与正式结果

本地补齐三项缺口：record.repeat与计划编号强制匹配；同方法三次重复的全部非计时逐轮字段/专属计数及0/1/2覆盖一致；按协议输出逐重复D/B、D/E范围。训练、认证、通信核心、配置与C1/C2/C3均未改。13项测试通过，18个smoke进程及完成后resume通过；6缓存标记、16历史锚点预检通过。详见[运行前审核](../../outputs/stl10_repeat_review_20261102/REVIEW.md)。

正式54/54运行、6块一致，62清单文件及67源码/协议摘要通过；关系530841600、候选707788800次oracle记录零错误。五份报表重生成逐字节一致，独立均值后配对及阈值重算通过。IID与强非IID均通过C1/C2/C3，但IID seed1001波动较大，机械确认不等于排除全部机器噪声。详见[正式审核](../../outputs/stl10_repeat_results_20261102/REVIEW.md)。全部计时保留，不与探索批次合并，不自动删除或替换波动数据。
