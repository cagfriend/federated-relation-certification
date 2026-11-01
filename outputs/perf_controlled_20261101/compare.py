import json,hashlib,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[2];H=Path(__file__).parent
lines=['# 插电环境下的异常组与正常组复测','','本次两组三元组各运行一次，沿用原repeat1顺序；属于受控环境复测，未替换正式预注册重复。','','|seed|方法|原rep0秒|原rep1秒|上次诊断秒|本次插电秒|','|---|---|---:|---:|---:|---:|'];evidence={}
for seed,previous in [(909,'perf_confirmation_rerun_20261101'),(808,'perf_confirmation_normal_rerun_20261101')]:
 d=R/f'outputs/perf_controlled_seed{seed}_20261101';done=json.loads((d/'completed.json').read_text());p=json.loads((R/'outputs'/previous/'completed.json').read_text());old={r['method']:r for r in p['comparison']};new={r['method']:r for r in done['comparison']};power=[json.loads(s) for s in (d/'power_log.jsonl').read_text().splitlines()]
 assert done['original_results_unchanged'] and done['all_method_signatures_identical_to_original']
 for m in ('B','E','D'):
  r=new[m];lines.append(f"|{seed}|{m}|{r['original_rep0_head_seconds']:.2f}|{r['original_rep1_head_seconds']:.2f}|{old[m]['rerun_head_seconds']:.2f}|{r['rerun_head_seconds']:.2f}|")
 evidence[str(seed)]=dict(D_B_saving_percent=100*(1-new['D']['rerun_head_seconds']/new['B']['rerun_head_seconds']),D_E_saving_percent=100*(1-new['D']['rerun_head_seconds']/new['E']['rerun_head_seconds']),power_samples=len(power),ac_status=sorted({x['ac_line_status'] for x in power}),battery_saver=sorted({x['battery_saver'] for x in power}),battery_percent_range=[min(x['battery_percent'] for x in power),max(x['battery_percent'] for x in power)])
for seed,e in evidence.items():lines+=['',f"seed{seed}：D/B省时{e['D_B_saving_percent']:.2f}%，D/E省时{e['D_E_saving_percent']:.2f}%；电源记录{e['power_samples']}次，AC状态{e['ac_status']}，电量范围{e['battery_percent_range']}，省电标记{e['battery_saver']}。"]
a=json.loads((R/'outputs/perf_confirmation_results_20261101/audit.json').read_text(encoding='utf-8'));assert all(hashlib.sha256((R/p).read_bytes()).hexdigest()==h for p,h in a['run_sha256'].items())
lines+=['','所有6次运行均与各自原非计时签名一致，原72份运行哈希未变。当前供电记录均为插电。正常组也恢复到接近原运行的耗时，较已记录未插电的诊断明显加快，支持供电/运行环境影响的解释；由于同时跨越运行时段且缺少频率/温度控制，不能将差值全部归因于电源。','','本次每组仅新增一次，不凑作原预注册的两次重复，也不更新GitHub排除口径。原强非IID909/2048暂排状态保留，待确定正式补测统计规则后再恢复。']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');(H/'comparison.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence,indent=2))
