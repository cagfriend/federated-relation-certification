# 云端验证记录（2026-11-01，推送前）

- 单元测试：`python -m unittest experiments.stl10_compute.test_run`
  5 项全过。覆盖：护栏适配器（健康记录全过；全单簇+ACC 10%+边比例
  99.9% 的退化记录 S1/Q1/Q2 判失败）；配对汇总的比值、省秒与胜出
  计数；正式矩阵 18 条/6 三元组、case_id 为 m16384_fixed2_privfull、
  smoke 矩阵 6 条。
- Smoke：`python -m experiments.stl10_compute.run --preset smoke`
  完成 6 条独立进程运行（seed1001 × 两划分 × B/E/D，夹具 M128、
  3 轮、公共 2 步）。三元组轨迹与指标等值检查通过；逐轮 oracle
  审计 mismatches=0（关系比较 2304、候选成员比较 3072）；报告、
  CSV、护栏表均生成。夹具轨迹本身未通过护栏属预期（合成数据无
  真实聚类结构），只验证机械流程。
- Resume：`--resume` 保留全部 6 条并重新执行全部校验与锚点逻辑，
  结果一致。
- 正式 preset 的双锚点（8 步迁移 B、长程 2 步 B）与 ACLineStatus=1
  门槛依赖用户本地的 results_full 目录，云端未跑正式矩阵；锚点
  加载路径与长程审阅中的预检口径一致（锚点先经各自 runner 的
  check_run 验证封签与完整性，再作比较）。
