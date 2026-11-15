# 后续材料与发布状态

更新2026-11-09。重构时只读快照已保留；本次正式补发P1/P2执行包、原始记录无损归档、报表与审核，原有目录不移动。下方旧快照清单仍指重构当时的证据，不代表最新完成状态。

## P1：已完成、审核并发布

8配置×B/E/D共24次200轮运行，加6次隔离内存回放。关系353,894,400、候选471,859,200次零错误。D/B完整头部8/8更快，D/E7/8更快；K64/IID/1101慢0.33%。每方法一次属探索性；两配置内存代价与准备污染保留。[正式报告](../../experiments/lr_compute/results_full/report.md) · [审核](../../outputs/lr_compute_results_20261106/REVIEW.md)

## P2：正式36次完成、审核并发布

四强非IID配置、各B/E/D三次，顺序平衡；530,841,600关系和707,788,800候选检查零错误。D/B配对中位省25.93%–40.87%，12/12重复更快；D/E中位省0.79%–8.47%，9/12更快，仅1/4配置通过预设3%门槛，合取通过1/4。三技术重复不是独立seed。原始异常不自动剔除，准备污染仍NA；没有新增隔离内存。[报告](../../experiments/lr_repeat/results_full/report.md) · [正式审核](../../outputs/lr_repeat_results_20261109/REVIEW.md)

## 原始记录与复现

两个执行包保持原路径。共60个主运行JSON按case无损ZIP保存，P1六份内存记录另存ZIP，[成员清单](../../archives/lr_followups_raw_20261109.manifest.json)记录恢复路径及SHA256；原环境、完成清单、电源日志和小报表直接保留。解压到仓库根目录后可核验原完成摘要。特征、数据、编码器和上游准备缓存不上传；新机器不能直接使用旧绝对路径resume。P1/P2的VALIDATION是实验前开发记录，正式状态以上述结果与审核为准。

## 快照清单

|本地原始路径|本次保存路径|SHA256|
|---|---|---|
|`experiments/lr_compute/results_full/report.md`|[docs/history/local_followups/experiments/lr_compute/results_full/report.md](../../docs/history/local_followups/experiments/lr_compute/results_full/report.md)|`007de319bde553732141268dcd277be4b9467b0292f6b218983c9eee6d2cecf7`|
|`outputs/lr_compute_results_20261106/REVIEW.md`|[docs/history/local_followups/outputs/lr_compute_results_20261106/REVIEW.md](../../docs/history/local_followups/outputs/lr_compute_results_20261106/REVIEW.md)|`7df3cd16b47b58abe4c33504dc97aac6ec703d002e8cf43c8f75b54cb6eb5b5c`|
|`outputs/lr_compute_results_20261106/audit.json`|[docs/history/local_followups/outputs/lr_compute_results_20261106/audit.json](../../docs/history/local_followups/outputs/lr_compute_results_20261106/audit.json)|`04a68884b8eed0ccbd11d4b5ae7655f73071868f2ba19f958fc178f0aa9eb4e9`|
|`experiments/lr_compute/PREREGISTRATION.md`|[docs/history/local_followups/experiments/lr_compute/PREREGISTRATION.md](../../docs/history/local_followups/experiments/lr_compute/PREREGISTRATION.md)|`bc32d94d68b540e872af9136526d03844f619c7521e8d802c55b2f52e0917b76`|
|`experiments/lr_repeat/PREREGISTRATION.md`|[docs/history/local_followups/experiments/lr_repeat/PREREGISTRATION.md](../../docs/history/local_followups/experiments/lr_repeat/PREREGISTRATION.md)|`50290a5e5f24c711b507f22d14c1b85b50045ce1643228c39e2f3247561152b6`|
|`experiments/lr_repeat/VALIDATION.md`|[docs/history/local_followups/experiments/lr_repeat/VALIDATION.md](../../docs/history/local_followups/experiments/lr_repeat/VALIDATION.md)|`e63816312ad889ee5ade86d7d66e5306c232a624281525f541060e4f10682253`|


## P3：正式完成并发布，2026-11-10

P3固定每客户端400张规模实验已完成：54次主运行+12次隔离内存回放；18/18配置D/B与D/E完整头部均更快，六组配对中位省时分别35.39%–43.57%和6.27%–16.53%。末轮18/18无严重退化，9/18早期配置在20/40轮曾有单簇或≥99%事件。相对B的峰值内存增加9.8%–26.2%，通信字节相同。

执行包[lr_client_scaling](../../experiments/lr_client_scaling/README.md)、[正式审核](../../outputs/lr_client_scaling_results_20261110/REVIEW.md)及[原始恢复清单](../../archives/lr_client_scaling_raw_20261110.manifest.json)已发布。66份主/内存JSON按N/seed无损ZIP保存，解压回原路径后校验completed.json全部102份文件；18输入指针、原电源/环境及报表直接保留。开发VALIDATION中的未启动标记是当时状态，不能覆盖正式完成证据。原数据、表示和模型缓存不上传，原机绝对路径不适用于异机resume。


## 数量异构：正式完成、正确性通过、学习范围受限，2026-11-11

私有数量异构54主+6内存已完成：D/B18/18更快、D/E16/18更快；两个IID/seed1002负收益保留。末轮严重退化equal0/6、moderate2/6、strong6/6，集中在低容量客户端；B/E/D轨迹一致，不归为认证新增损失。

[执行包](../../experiments/quantity_heterogeneity/README.md) · [审核](../../outputs/quantity_heterogeneity_results_20261111/REVIEW.md) · [原始60记录清单](../../archives/quantity_heterogeneity_raw_20261111.manifest.json)。10个无损ZIP恢复原路径后可核对79份完成文件；原环境中保存18份输入身份，数据与特征缓存不上传。VALIDATION未启动字段为开发时状态，正式结论以本轮审核为准。


## 低容量诊断正式完成并发布，2026-11-12

低容量诊断已完成4条40轮基线回放和8条200轮B诊断。基线逐轮匹配旧轨迹；private-only、全体公共LR0.0125均4/4通过160/180/200逐客户端解除严重退化检查。低LR的100张客户端最大簇仍最高97.89%，不等于充分健康聚类，也没有认证省时结论。

[执行包](../../experiments/low_capacity_diagnostic/README.md) · [审核](../../outputs/low_capacity_diagnostic_results_20261112/REVIEW.md) · [恢复清单](../../archives/low_capacity_diagnostic_20261112.manifest.json)。12原始JSON及4大CSV分5个无损ZIP保存，按清单恢复后可核验27份完成文件；输入身份/公共探针ID存在环境和JSON中，真实数据/模型/特征缓存不上传。VALIDATION的未启动标记是开发时状态，不代表本轮正式结果仍未完成。


## E28：局部公共步幅的单配置证据，2026-11-12

strong/IID/seed1001局部公共LR干预完成：仅100张client0/3降至0.0125，其余仍0.05；局部分支160/180/200全部6客户端通过严重退化检查，原0.05持续单簇。局部早期40/60/80轮仍双单簇，属于晚期解除持续退化，不是防止坍缩或充分健康保证。

仅私有训练也存在早期单簇，因此公共更新不是早期坍缩的必要条件；更符合当前证据的解释是公共步幅参与维持/延迟解除退化。局部分支晚期私有拟合变化均值+0.34146个百分点、公共更新−0.20732个百分点；这些逐轮描述不是独立统计样本或唯一根因证明。全局低LR与private-only历史参照同样晚期通过。[完整审核](../../outputs/local_public_lr_results_20261112/REVIEW.md)。下一步只确认剩余3个既有配置，不追加学习率档位；通过后另行验证同轨迹计算成本。


## E29 局部公共步幅的三配置质量确认，2026-11-13

局部公共LR剩余三配置确认已完成：seed1001/α0.1、seed1002/IID及α0.1各200轮B；160/180/200全部6客户端检查为3/3配置、54/54项通过。此前1001/IID探索单列。早期严重集中仍存在，解除严重退化不等于充分健康聚类；本轮不使用计时或加速结论。

仅100张client0/3的有效公共LR设0.0125，其余0.05。与E28探索共同构成有限四配置观察，确认分母仍单列3。原0.05历史小客户端持续严重集中；局部与全体降LR晚期表现接近，未作统计等效检验。所有早期事件、低NMI与仅私有更低集中程度均保留。[完整审核](../../outputs/local_public_lr_confirmation_results_20261113/REVIEW.md)。后续恢复同一局部规则的B/E/D精确性和资源比较，不能沿用本轮带探针的B计时。


## E30/E31 私有校正与同轨迹计算验证，2026-11-13

私有伪簇频数校正四条B协作轨迹全部通过：两个小客户端最后40轮平均同簇边由63.4%–82.5%降至17.9%–22.9%，末轮测试最大簇为23.2%–37.6%。保持既定学习率和更新预算，早期7–11轮高度集中仍存在，结论为两个既有seed的探索性证据。

私有校正后的四环境B/E/D共12次主运行及6次隔离内存回放完成，关系/参数/质量精确一致，117,964,800次关系与157,286,400次候选检查零错误。D/B完整头部省35.25%–43.00%，D/E省10.31%–14.12%；通信字节相同，两个内存配置D/B峰值增加约14.5%。每环境每方法一次。

[质量审核](../../outputs/private_prior_results_review/REVIEW.md) · [计算审核](../../outputs/private_prior_compute_results_review/REVIEW.md) · [后续联合确认](../NEXT_EXPERIMENTS.md)。历史不利配置与噪声边界继续保留。



## E32 新种子联合确认，2026-11-14

新seed1201/1202/1203 × 两划分 × B/E/D各3次重复，共54次独立进程完成。IID完整头部D/B、D/E中位省时39.08%/16.67%，强非IID为39.29%/12.45%；预定性能及质量条件全部通过，逐轮匹配各case全量B参考。 [审核](../../outputs/private_prior_confirmation_review/REVIEW.md)

12小端末40轮同簇边13.85%–24.50%，晚期护栏全部通过。两例client1在第20轮近单簇仍保留。正式无oracle，逐轮与各case全量B参考核对。原浮点、空间与范围边界继续保留。下一步建议500轮长期稳定性验证。
