# 已完成实验：仅保留结果与记录

2026-10-29按用户要求清理本目录的Python运行程序、测试和编译缓存。原结果、环境配置、审计、准备缓存与官方数据保持原样；原README中的历史运行命令不再适用。

当前实验入口为 `python -m experiments.public_scaling.run`，说明见 `../public_scaling/README.md`。新实验继续读取本目录下的官方数据文件，新的固定公共池准备缓存独立放在public_scaling中，不混用旧私有分区。

清理清单及原文件哈希见 `../../outputs/experiment_cleanup_20261029/`；历史source manifest中的已移除源码路径保留作记录。
