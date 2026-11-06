# 公共学习率0.05初步确认

每配置单列原0.1参照与0.05候选。历史和新运行的来源见records及clients.csv。

|配置|角色|最终结构|过程|NMI地板|适用ACC护栏|总体|
|---|---|---|---|---|---|---|
|n12_k10_dirichlet_0.1_seed1001|healthy|True|True|True|True|True|
|n12_k10_dirichlet_0.1_seed1003|known_failure|True|True|True|None|True|
|n12_k10_iid_seed1101|new_seed|True|True|True|True|True|
|n12_k10_dirichlet_0.1_seed1101|new_seed|True|True|True|True|True|
|n6_k64_dirichlet_0.1_seed1001|healthy|True|True|True|True|True|
|n6_k64_dirichlet_0.1_seed1002|known_failure|True|True|True|None|True|
|n6_k64_iid_seed1101|new_seed|True|True|True|True|True|
|n6_k64_dirichlet_0.1_seed1101|new_seed|True|True|True|None|True|

|配置|分支|来源|最终ACC|最终NMI|平均最大簇占比|≥99%客户端|
|---|---|---|---:|---:|---:|---:|
|n12_k10_dirichlet_0.1_seed1001|reference2|historical|0.175417|0.064181|0.356052|0/12|
|n12_k10_dirichlet_0.1_seed1001|public2_half|new|0.178510|0.067855|0.332302|0/12|
|n12_k10_dirichlet_0.1_seed1003|reference2|historical|0.108865|0.011711|0.962365|3/12|
|n12_k10_dirichlet_0.1_seed1003|public2_half|historical|0.177969|0.077291|0.349979|0/12|
|n12_k10_iid_seed1101|reference2|new|0.186677|0.084549|0.315365|0/12|
|n12_k10_iid_seed1101|public2_half|new|0.187323|0.086124|0.296958|0/12|
|n12_k10_dirichlet_0.1_seed1101|reference2|new|0.176281|0.077954|0.377687|0/12|
|n12_k10_dirichlet_0.1_seed1101|public2_half|new|0.178521|0.079279|0.351573|0/12|
|n6_k64_dirichlet_0.1_seed1001|reference2|historical|0.171437|0.067738|0.386937|0/6|
|n6_k64_dirichlet_0.1_seed1001|public2_half|new|0.176708|0.071797|0.332563|0/6|
|n6_k64_dirichlet_0.1_seed1002|reference2|historical|0.100000|0.000000|1.000000|6/6|
|n6_k64_dirichlet_0.1_seed1002|public2_half|new|0.188729|0.085227|0.306812|0/6|
|n6_k64_iid_seed1101|reference2|new|0.183542|0.084516|0.394062|0/6|
|n6_k64_iid_seed1101|public2_half|new|0.186479|0.091143|0.318167|0/6|
|n6_k64_dirichlet_0.1_seed1101|reference2|new|0.110958|0.008112|0.924687|4/6|
|n6_k64_dirichlet_0.1_seed1101|public2_half|new|0.171458|0.090627|0.433500|0/6|

过程指标使用20轮起的共同检查点；12轮smoke的过程列仅用于验证数据通路。
新seed1101只有一个随机实例，两个划分单列。历史已知退化配置属于修复范围验证。
原始records保存阶段探针、教师同簇边率、完整簇分布和来源摘要，按完整过程解释每项判定。
