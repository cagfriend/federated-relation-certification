# 云端验证记录（perf_confirmation）

日期：2026-10-31。环境：云端 Linux VM（4 核 CPU、无 GPU），venv 含
torch 2.15.0+cpu / numpy 2.5.4 / scipy 1.18.1 / scikit-learn 1.9.1
（与正式运行的本机环境不同，此处只验证代码路径，不产性能证据）。

- 单元测试：`python -m unittest experiments.perf_confirmation.test_confirmation`
  4 项全部通过：档位/seed/重复冻结、日程平衡（24 三元组每方法领跑 8 次）、
  组级轨迹一致性与篡改/漂移检出、聚合与 C1/C2/C3 判定（正例确认、反例否决）。
- 官方 smoke：`python -m experiments.perf_confirmation.run --preset smoke`
  全流程完成：24 次独立进程运行（2 划分 × 1 seed × 2 档位 × 3 方法 ×
  2 重复）、4 组组级核对全部通过（组内 6 次运行非计时字段逐轮一致、
  同方法两次重复连教师前向端点/认证边数等专属计数也完全一致），
  mismatches=0，9216 次关系比较、12288 次候选成员比较；报表与完成
  凭据生成。smoke 为毫秒级小规模，配对比值无性能含义。
- Resume 验证：同一 smoke 以 `--resume` 重跑，24/24 显示
  `preserved completed run` 并再次完成。
- 开发中修正的一处口径：oracle 的候选成员比较只对 E/D 计数
  （B 不审计候选集），单方法运行的期望值按方法区分（B 为 0，
  E/D 为 rounds×clients×samples）；跨方法轨迹签名只含关系比较数，
  候选成员数在同方法重复签名中核对。正式设计不受影响。

正式 full 运行（新 seed 707/808/909 的准备 + 72 次运行）由用户在本机
执行；云端未跑正式计时。
