import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
out=[]
for package in ('real_iid','public_scaling','graph_density','noniid_clustering','public_budget','private_workload','perf_confirmation','stl10_transfer'):
 d=ROOT/'experiments'/package/'results_full';found={}
 for p in sorted(d.rglob('*.json')):
  if p.name.startswith(('memory','prepared','environment','completed','finished','invocation')):continue
  r=json.loads(p.read_text(encoding='utf-8'));sm=r.get('summary',{})
  if not isinstance(sm,dict):continue
  for method in ('B',):
   s=sm.get(method)
   if not isinstance(s,dict):continue
   q=s.get('final_metrics')
   if not isinstance(q,dict) or not q.get('clients'):continue
   key=(r.get('partition','iid'),r.get('seed'),r.get('case_id',r.get('config',{}).get('samples')))
   found.setdefault(key,dict(file=str(p.relative_to(ROOT)),q=q,config=r.get('config'),spec=r.get('spec')))
 if found:
  cs=[c for x in found.values() for c in x['q']['clients']];acc=[x['q']['mean']['acc'] for x in found.values()]
  out.append(dict(package=package,unique_B_configurations=len(found),mean_acc_range=[min(acc),max(acc)],client_cases=len(cs),single_cluster=sum(c['occupied_clusters']==1 for c in cs),dominant_99=sum(c['largest_cluster_fraction']>=.99 for c in cs),details=list(found.values())))
(Path(__file__).parent/'HISTORICAL_QUALITY.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
print(json.dumps([{k:v for k,v in x.items() if k!='details'} for x in out],indent=2))
