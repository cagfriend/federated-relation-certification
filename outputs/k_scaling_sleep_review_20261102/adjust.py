"""Derived exclusions only: never overwrites sealed experiment records."""
import csv,json
from pathlib import Path
ROOT=Path.cwd();R=ROOT/'experiments/k_scaling/results_full';O=ROOT/'outputs/k_scaling_sleep_review_20261102';D=O/'sleep_adjusted';D.mkdir(exist_ok=True)
a=json.loads((O/'audit.json').read_text(encoding='utf-8'));bad=a['affected_preparation']
def affected(row):return int(row['seed'])==1002 and row['partition']=='dirichlet_0.1' and int(row['classes'])==64
def process(name):
 with (R/name).open(encoding='utf-8',newline='') as f:
  reader=csv.DictReader(f);fields=list(reader.fieldnames)+['preparation_status'];rows=list(reader)
 for row in rows:
  row['preparation_status']='unavailable_confirmed_preparation_sleep' if affected(row) else 'retained'
  if affected(row):
   for key in ('additional_kmeans_seconds','additional_preparation_seconds','with_preparation_ratio'):
    if key in row:row[key]=''
 with (D/name).open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 return sum(affected(row) for row in rows)
masked_runs=process('runs.csv');masked_pairs=process('paired_cost.csv')
assert masked_runs==3 and masked_pairs==2
report=(R/'report.md').read_text(encoding='utf-8')
prefix='''> 休眠影响处理版：全部方法头部计时保持不变。seed1002、强非IID、K64的共享新增准备成本受休眠污染；本目录CSV将3方法该成本及2个含准备比值留空，不以零填充、不估补正常耗时。原始报告和封签未改。下列主表只比较完整头部时间，数值因此与原表一致。

> 补充质量审核：同一个强非IID/seed1002/K64配置最终6/6客户端单簇，B/E/D完全一致。主表保留该配置的成本数据并标明其适用范围；不能将其当作有效聚类上的成功迁移，也不能用准备期休眠解释或删除K64的D/E劣势。详细逐配置质量见../../k_scaling_results_20261102/quality.csv。

'''
(D/'report.md').write_text(prefix+report,encoding='utf-8')
record=dict(excluded_training_rounds=[],excluded_method_runs=[],contaminated_preparation_case=bad,
 affected_methods=['B','E','D'],masked_preparation_rows=3,masked_with_preparation_comparisons=2,
 training_timing_changed=False,no_numerical_sleep_subtraction=True,no_counterfactual_imputation=True,
 raw_results_unchanged=True,reason='Confirmed user sleep plus Windows wake event and 675s KMeans fit anomaly. Different clock intervals cannot safely be subtracted.')
(O/'EXCLUSION.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print('Derived only: masked 3 shared-preparation rows and 2 preparation-inclusive comparisons; 0 training rounds removed.')
