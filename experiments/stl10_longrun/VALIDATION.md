# 云端验证记录（2026-11-01，推送前）

环境：云端 Linux，仓库 venv（numpy/scipy/sklearn/torch 与冻结运行时
字段一致性由 runner 的 environment 检查承担）。

- 单元测试：`python -m unittest experiments.stl10_longrun.test_design`
  14 项全过。覆盖：完整/ smoke 检查点集合；S1 三条件（含“均值合格但
  单客户端 99.5% 仍判失败”、单簇客户端判失败）；S2 自第 20 轮起判定
  （早期单簇只警告）、第 20 轮大面积坍缩判失败；Q1/Q2 边界；选档
  三分支（两档都过→2、仅 2 过→2、仅 1 过→1、都不过→None）；
  正式矩阵 8 条、smoke 矩阵 4 条。
- Smoke：`python -m experiments.stl10_longrun.run --preset smoke`
  完成 4 条轨迹（seed1001 × 两划分 × 1/2 步，12 轮，合成夹具，
  每条独立进程）。检查点集合实测 [0,1,2,5,10,12]；逐轮公共步数
  = 客户端数 × 档位步数，封签与 check_run 全过；事件日志带
  warning_only 标记；私有伪标签拟合、私有工作量字段均有记录。
  夹具轨迹本身全部未通过标准（合成数据无聚类结构），报告已标注
  只验证机械流程，不构成结论。
- Resume：`--resume` 复跑保留全部 4 条轨迹并重新执行 check_run
  与报告生成，结果一致。
- 正式 preset 的锚定检查（初始头/图摘要、私有工作量字段 vs 历史
  8 步 B 运行）与 ACLineStatus=1 门槛只能在用户本地（Windows +
  results_full + 准备缓存）验证，云端未跑正式矩阵。
