from pathlib import Path
import json,statistics,csv
H=Path(__file__).parent;R=H.resolve().parents[1];O=R/'experiments/low_capacity_diagnostic/results_full'
a=json.loads((H/'audit.json').read_text(encoding='utf-8'));assert a['status']=='PASS'
records=[json.loads(p.read_text(encoding='utf-8')) for p in (O/'runs').glob('*.json')]
derived=[]
for branch in ('baseline','private_only','low_lr'):
 rs=[r for r in records if r['branch']==branch]
 obs=[c for r in rs for d in r['diagnostic_records'] if d['round']<=40 for c in d['clients'] if c['client'] in (0,3)]
 derived.append(dict(branch=branch,client_rounds=len(obs),private_fit_delta_pp=100*statistics.mean(c['T1']['private']['fixed_pseudo_fit']-c['T0']['private']['fixed_pseudo_fit'] for c in obs),public_fit_delta_pp=100*statistics.mean(c['T2']['private']['fixed_pseudo_fit']-c['T1']['private']['fixed_pseudo_fit'] for c in obs),public_concentration_delta_pp=100*statistics.mean(c['T2']['public']['largest_cluster_fraction']-c['T1']['public']['largest_cluster_fraction'] for c in obs),public_fit_decrease_count=sum(c['T2']['private']['fixed_pseudo_fit']<c['T1']['private']['fixed_pseudo_fit'] for c in obs)))
with (H/'early_stage_summary.csv').open('w',encoding='utf-8',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(derived[0]));w.writeheader();w.writerows(derived)
text='''# 低容量客户端诊断：正式结果审核

2026-11-12。依据GitHub计划8f8e7554：strong四配置（seed1001/1002×IID/α0.1），先4条40轮B基线回放，再8条200轮诊断。复用原ID/表示/伪标签/初始头/图；本轮不产出认证省时结论。

## 核验与冻结判据

27份完成文件与finished封印、107份冻结来源/协议、旧数量实验99份源码、4份缓存及历史参考均通过核验。4条baseline前40轮全部原非计时账本、目标/关系统计、头摘要、损失及20/40测试指标与历史精确匹配。11份报表逐字节重生成一致；10,560条逐轮客户端三时点观测经容量/预测直方图/顺序/阶段连续性/private-only零更新等核验。

|分支|执行量|恢复判定|
|---|---|---|
|原公共LR0.05|4×40轮|短回放匹配通过；历史200轮四配置仍为严重退化参考|
|private-only|4×200轮|4/4配置通过|
|全客户端公共LR0.0125，仍2步|4×200轮|4/4配置通过|

“通过”严格指160/180/200三个测试点，六客户端逐个均非单簇且最大簇<99%；两个100张客户端0/3及400/700张客户端均检查。不是末轮平均替代，也不设置ACC增益或临时NMI阈值。

两个100张客户端在三个晚期检查点（每分支24个客户端-检查点）的实测范围：private-only最大簇57.46%–92.04%、NMI0.01497–0.08336；低LR最大簇64.99%–97.89%、NMI0.01291–0.05861。部分预测仍高度集中，低LR并未证明充分健康聚类；解除严重退化是本轮阈值结论。

## 三时点机制观测

对每分支前40轮、四配置中的两个100张客户端，共320个客户端-轮次做描述性汇总（不是320个独立实验单位）：

|分支|私有步拟合率变化均值/百分点|公共步拟合率变化均值/百分点|公共步公共探针最大簇变化均值/百分点|公共步降低私有拟合的次数|
|---|---:|---:|---:|---:|
'''
for d in derived:text+=f"|{d['branch']}|{d['private_fit_delta_pp']:.5f}|{d['public_fit_delta_pp']:.5f}|{d['public_concentration_delta_pp']:.5f}|{d['public_fit_decrease_count']}/320|\n"
text+='''
当前轨迹中私有更新的平均拟合变化为正，公共更新可在部分轮次降低拟合并增加公共探针集中；低公共LR下这些描述性平均变化减弱。不是每轮/每客户端都如此，且不同分支T1模型和教师目标随训练分化，不能仅用均值作单因素归因。范数只表变化大小，不单独代表更新方向或破坏性。

## 允许的因果解释与限制

在相同缓存/初始化及其他训练规则下，关闭公共更新和全局降低公共LR都解除本矩阵严重退化，增加了“公共协作更新参与形成或维持退化”的干预证据。private-only无同类持续严重退化，因此本矩阵没有显示该退化在无公共更新时同样出现。但它不能排除私有表示/伪标签参与易感性，也不能证明小客户端自己的公共步幅是唯一原因：全体客户端降LR同时改变了其他客户端未来提供的教师关系。

0.05基线仅新增1–40轮的三时点日志。历史160–200轮只有原已保存测试/账本字段，T0/T1/T2等新增历史字段为NA；没有用短回放或新分支推算填充。当前公共探针来自训练公共池，是固定诊断子集，不是独立泛化集；恢复判定仍用原测试集。

## 电源和计时

60条AC采样均在线、无间隔告警；阶段粗筛没有超过max(2秒,阶段中位数10倍)的异常，未剔除任何运行或轮次。仪器化计时和诊断开销单列，不与历史B/E/D计时混合，不作认证省时、能耗或频率/温度恒定结论。

## 下一步建议（未冻结/未写代码）

按既定条件分流，现在可以在一个已复现配置strong/IID/seed1001上仅降低两个100张客户端0/3的公共LR到0.0125，其余客户端仍0.05；复用现有全局低LR/private-only和历史0.05作为参照。用于区分小客户端本地步幅与耦合教师反馈，不是马上扩大规模或新增加权/损失。

若要解释该单配置160–200轮与原0.05的三时点机制差异，应另加同配置完整0.05诊断回放；当前40轮基线不够。具体矩阵/判据需运行前另行冻结。候选稳定后再恢复同一新轨迹的B/E/D计算比较，本轮没有证明低LR下的D省时。

[机器审计](audit.json) · [审计脚本](audit_results.py) · [前40轮描述统计](early_stage_summary.csv) · [独立复审](INDEPENDENT_REVIEW.md) · [原报告](../../experiments/low_capacity_diagnostic/results_full/report.md) · [预注册](../../experiments/low_capacity_diagnostic/PREREGISTRATION.md)。原结果、旧源码不改，新增审阅材料不重写原判据。
'''
(H/'REVIEW.md').write_text(text,encoding='utf-8');print(H/'REVIEW.md')
