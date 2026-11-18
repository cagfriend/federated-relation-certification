# STL-10 编码器快照实验

全部训练分支复用中心初始化、全客户端私有频数校正、全程 0.5 间隔保护以及原有公共关系训练。候选选择只使用私有伪簇计数和无标签公共占用。

| 实验 | 原始结果 |
|---|---|
| 自编码器逐步重放 | [逐步报告](../encoder_collapse_probe/results_pilot/report.md) |
| Seed 1201 的 40 轮配对 | [对照报告](results_pilot/report.md) |
| 三个新种子的固定第 3/4 步对照 | [200 轮报告](results_confirmation/report.md) |
| 五个新种子的无标签筛选、1204 client2 恢复 | [筛选报告](results_selection_validation/report.md) |
| 1207、1208 的全客户端筛查与回退 | [回退报告](results_fallback_validation/report.md) |

结果包括逐轮记录、逐客户端测试检查点、候选选择、失败状态和校验摘要。复现实验需要 STL-10 原始二进制文件，默认读取 `experiments/stl10_transfer/data/stl10_binary`。数据准备可用 `experiments.stl10_transfer.data.ensure_data`。准备缓存和模型权重由脚本在本地生成。已核对的环境为 Python 3.12.7、NumPy 1.26.4、SciPy 1.13.1、scikit-learn 1.5.1、PyTorch 2.7.1+cu118、threadpoolctl 3.5.0，训练用单线程 CPU。历史对照和回执使用精确摘要，复现时应使用相同数值环境。

从仓库根目录执行下面的命令。

```text
python -B -m experiments.encoder_early_stop.prepare_replay_cache probe
python -B -m experiments.encoder_collapse_probe.run --preset pilot --partition iid dirichlet_0.1 --output local_replays/encoder_probe
python -B -m experiments.encoder_early_stop.confirm --output local_replays/fixed_steps
python -B -m experiments.encoder_early_stop.prepare_replay_cache selection
python -B -m experiments.encoder_early_stop.validate_selection --output local_replays/snapshot_selection
python -B -m experiments.encoder_early_stop.prepare_replay_cache fallback
python -B -m experiments.encoder_early_stop.validate_fallback --output local_replays/client_fallback
```

40 轮脚本 `experiments.encoder_early_stop.run` 还需要原 E36 完整轨迹，用于逐轮验对照前缀。仓库保留已验收的 40 轮历史结果。本地重新执行的输出用单独目录保存。

[方法与适用边界](../../docs/method/encoder_snapshot_selection.md)
