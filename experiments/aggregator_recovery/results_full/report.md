# 临时聚合者交接/恢复：协议成本实验

已完成18组配置-seed。completed.json经校验存在才算全套完成。

只研究真实序列化的内存传输协议，不是模型训练或实际网络；synthetic trace是合法同簇关系，不是已训练模型的输出。

|场景|策略/全量重建|总字节比|故障/交接轮字节比|
|---|---|---:|---:|
|control_sparse|on_demand|1.00000|N/A|
|control_sparse|hot_backup|1.17640|N/A|
|crash_dense|on_demand|1.00000|1.00000|
|crash_dense|hot_backup|1.23053|1.21962|
|crash_down_sparse|on_demand|1.00000|1.00000|
|crash_down_sparse|hot_backup|1.09308|1.01449|
|crash_upload_sparse|on_demand|1.00000|1.00000|
|crash_upload_sparse|hot_backup|1.17614|1.05425|
|frequent_crash|on_demand|1.00000|1.00000|
|frequent_crash|hot_backup|1.12222|1.01495|
|handoff_sparse|on_demand|1.00173|1.06524|
|handoff_sparse|hot_backup|1.17315|1.06524|

主比较是总字节，含setup、投票/换届、正常复制、失败尝试、重试、重新入组及ACK。事件轮字节含该轮正常数据和提交，不是纯快照大小；无事件场景用N/A。

本地wall time是序列化/解码/状态处理时间，不含网络传播、故障检测等待、真实选举超时或模型重训练，不能叫部署恢复时延。恢复计时含失败尝试和重试至首次新目标提交；同轮公共训练不存在。

hot_backup是扩展对照，不是当前方法默认。必须同时看正常复制成本与故障频率；不保证比rebuild或on_demand节省。只测持久数组字节，未测进程峰值或Python对象内存。

失效成员退出目标分母，重新加入后只贡献当前轮；保存的目标摘要可由输入seed和代码重新构造核验。不覆盖提交决议传播中崩溃、网络分区、拜占庭或候补同步失败。
