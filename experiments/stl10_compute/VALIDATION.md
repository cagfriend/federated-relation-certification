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


## 本地补充验证及正式结果

原云端5项测试未覆盖长程锚点索引顺序，也未实际覆盖README指定旧smoke源的缓存路径。本地审阅发现并修复：三元组键(partition,seed)与长程锚点键(seed,partition)不一致导致静默跳过；旧smoke记录错误使用新缓存身份导致报错。新包以verify_triples统一核验，强制锚点缺失即报错；旧smoke按其自身缓存身份校验。未修改学习/认证/协议核心或冻结预算。

新增回归后9/9项测试通过；带旧source-results的6条smoke独立运行及resume通过（关系2304、候选3072比较，零错误）。正式运行前6缓存、6旧8步锚点、4长程2步锚点校验通过。证据：[运行前审核](../../outputs/stl10_compute_review_20261101/REVIEW.md)、[本地补丁](../../outputs/stl10_compute_review_20261101/LOCAL_FIX.patch)。

正式18/18运行、6/6三元组通过，27文件摘要和61源码/协议摘要通过；关系176947200、候选235929600次oracle记录零错误，6条质量护栏全部通过。6份报表重生成逐字节相同。结果为探索性单次计时，详见[报告](results_full/report.md)和[正式审核](../../outputs/stl10_compute_results_20261101/REVIEW.md)。
