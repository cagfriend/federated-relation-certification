import json,statistics
from pathlib import Path
H=Path(__file__).parent
normal=json.loads((H/'completed.json').read_text());abnormal=json.loads((H.parent/'perf_confirmation_rerun_20261101/completed.json').read_text())
a={r['method']:r for r in normal['comparison']};b={r['method']:r for r in abnormal['comparison']}
logs=[json.loads(s) for s in (H/'power_log.jsonl').read_text().splitlines()]
lines=['# 正常三元组的电池供电诊断重跑','','强非IID、seed808、2048档、原repeat1顺序B/E/D。与seed909诊断重跑比较，全部原始72次结果保留。','','|方法|seed808原两次平均秒|seed808本次秒|较自身原均值变慢|seed909上次重跑秒|','|---|---:|---:|---:|---:|']
for m in ('B','E','D'):
 r=a[m];old=statistics.mean([r['original_rep0_head_seconds'],r['original_rep1_head_seconds']]);lines.append(f"|{m}|{old:.2f}|{r['rerun_head_seconds']:.2f}|{100*(r['rerun_head_seconds']/old-1):.2f}%|{b[m]['rerun_head_seconds']:.2f}|")
lines+=['',f"本次D/B省时{100*(1-a['D']['rerun_head_seconds']/a['B']['rerun_head_seconds']):.2f}%，D/E省时{100*(1-a['D']['rerun_head_seconds']/a['E']['rerun_head_seconds']):.2f}%。seed909重跑相应为23.73%和2.58%。",'',f"系统电源记录{len(logs)}次，ACLineStatus集合{sorted(set(x['ac_line_status'] for x in logs))}（0=未插电），电量{min(x['battery_percent'] for x in logs)}–{max(x['battery_percent'] for x in logs)}%，省电标记集合{sorted(set(x['battery_saver'] for x in logs))}。",'', '全部方法非计时签名与各自原结果一致，原始72次文件哈希未改变。正常组也共同变慢，说明现象并非seed909独有；电池功耗限制是合理解释，但原实验未记录电源/频率且两个seed轨迹不同，不能由此单独证明供电因果。未替换预注册重复，未重算正式判定。若需确认电源因果，应使用同一seed808三元组、相同电源模式再做插电配对。']
(H/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps(dict(normal_head_slowdown={m:a[m]['rerun_head_seconds']/statistics.mean([a[m]['original_rep0_head_seconds'],a[m]['original_rep1_head_seconds']])-1 for m in a},ac=set(x['ac_line_status'] for x in logs).__repr__(),battery_range=[min(x['battery_percent'] for x in logs),max(x['battery_percent'] for x in logs)])))
