from pathlib import Path
import sys,json,tempfile,statistics
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from experiments.public_lr_confirmation.run import read,environment_check,envelope_check,check_pair,digest,check_reference
from experiments.public_lr_confirmation.design import spec_for,verdict
from experiments.public_lr_confirmation.report import reports
out=Path('experiments/public_lr_confirmation/results_full');dest=Path('outputs/public_lr_confirmation_results_20261106');env=read(out/'environment.json');environment_check(env)
completed=read(out/'completed.json')
for name,value in completed['files'].items():assert digest(out/name)==value,name
assert read(out/'finished.json')['completed_manifest_sha256']==digest(out/'completed.json')
records={};summaries=[]
for case in env['cases']:
 spec=spec_for(env['preset'],case['family'],env['device'])
 pre=read(out/'preflight'/f"{case['case_id']}.json")
 from experiments.public_lr_confirmation.run import check_seal
 check_seal(pre)
 for arm in ('reference2','public2_half'):
  item=read(out/'records'/f"{case['case_id']}_{arm}.json");envelope_check(item,case,arm,spec,out);records[case['case_id'],arm]=item
 check_reference(pre,records[case['case_id'],'reference2']['result']);check_pair(case,spec,records)
 b=records[case['case_id'],'reference2']['result'];d=records[case['case_id'],'public2_half']['result']
 common=set(m['round'] for m in b['metrics'])&set(m['round'] for m in d['metrics']); detail=[]
 for arm,r in [('reference2',b),('public2_half',d)]:
  last=r['metrics'][-1];cs=last['clients'];near=[(m['round'],c['client']) for m in r['metrics'] for c in m['clients'] if c['largest_cluster_fraction']>=.99]
  detail.append(dict(arm=arm,origin=records[case['case_id'],arm]['origin'],final_metrics=last['mean'],final_mean_largest=statistics.mean(c['largest_cluster_fraction'] for c in cs),final_worst_largest=max(c['largest_cluster_fraction'] for c in cs),final_near=sum(c['largest_cluster_fraction']>=.99 for c in cs),final_single=sum(c['occupied_clusters']==1 for c in cs),min_acc=min(c['acc'] for c in cs),near_rounds=sorted(set(x[0] for x in near)),common_grid_near_events=sum(c['largest_cluster_fraction']>=.99 for m in r['metrics'] if m['round'] in common for c in m['clients']),verdict=verdict(r),final_teacher_fraction=r['round_records'][-1]['positive_relation_fraction']))
 summaries.append(dict(**case,arms=detail,acc_delta=d['metrics'][-1]['mean']['acc']-b['metrics'][-1]['mean']['acc']))
with tempfile.TemporaryDirectory(dir=dest) as tmp:
 reports(Path(tmp),env['cases'],records); names=[]
 for p in Path(tmp).iterdir():assert p.read_bytes()==(out/p.name).read_bytes(),p.name;names.append(p.name)
power=[json.loads(x) for p in out.glob('power_*.jsonl') for x in p.read_text(encoding='utf-8').splitlines()];warnings=[x for x in power if x['gap_warning'] or x['ac_line_status']!=1]
result=dict(status='PASS',records=len(records),new=sum(v['origin']=='new' for v in records.values()),historical=sum(v['origin']=='historical' for v in records.values()),pairs=len(env['cases']),manifest_files=len(completed['files']),sources=len(env['sources']),preflights=8,reports_reproduced=names,all_candidate_verdicts_passed=all(x['arms'][1]['verdict']['passed'] for x in summaries),all_mean_acc_increased=all(x['acc_delta']>0 for x in summaries),summary=summaries,power_samples=len(power),power_warnings=warnings,excluded_runs=0,excluded_rounds=0)
(dest/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k!='summary'}));print(json.dumps(summaries))
