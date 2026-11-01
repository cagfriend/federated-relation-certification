"""Change public SGD steps only; keep the complete teacher graph unchanged."""
import argparse
import csv
from dataclasses import replace
import json
from pathlib import Path
import time
from threadpoolctl import threadpool_limits
from experiments.stl10_transfer.run import check_environment,check_run,digest,seal
from experiments.stl10_transfer.data import verify
from experiments.public_scaling.data import Prepared
from experiments.private_workload.design import spec_from_json
from experiments.stl10_diagnostics.run import drive,compare_anchor,write

ROOT=Path(__file__).resolve().parents[2]
def budgets(preset):return (1,2,4,8) if preset=='full' else (1,2,4)
def sources():
 return {str(p.relative_to(ROOT)):digest(p) for folder in ('stl10_public_steps','stl10_diagnostics') for p in sorted((ROOT/'experiments'/folder).glob('*.py'))}

def validate(result,spec,rounds):
 cfg=spec.config;n=len(cfg.dimensions)
 if len(result['round_records'])!=rounds:raise ValueError('Incomplete rounds')
 for rnd,row in enumerate(result['round_records'],1):
  if row['round']!=rnd:raise ValueError('Round sequence differs')
  if row['public_optimizer_steps']!=n*spec.steps:raise ValueError('Incorrect public update count')
  if row['public_edges_consumed']!=n*spec.steps*cfg.public_edge_batch:raise ValueError('Incorrect public edge budget')
  if any(t['kind']!='dynamic' for t in row['student_targets']):raise ValueError('Teacher targets must refresh dynamically')

def reports(out,results):
 rows=[];stage_rows=[];gradient_rows=[]
 for steps,result in results.items():
  for q in result['metrics']:
   cs=q['clients']
   rows.append(dict(public_steps=steps,round=q['round'],acc=q['mean']['acc'],nmi=q['mean']['nmi'],ari=q['mean']['ari'],single_cluster_clients=sum(c['occupied_clusters']==1 for c in cs),dominant_99_clients=sum(c['largest_cluster_fraction']>=.99 for c in cs)))
  for r in result['stages']:
   for phase in ('before_private','after_private','after_public'):
    for c in r[phase]:
     for split in ('private','public'):
      p=c[split];stage_rows.append(dict(public_steps=steps,round=r['round'],phase=phase,client=c['client'],split=split,occupied_clusters=p['occupied_clusters'],largest_cluster_fraction=p['largest_cluster_fraction'],mean_confidence=p['mean_confidence'],pseudo_accuracy=p.get('pseudo_accuracy'),pseudo_ce=p.get('pseudo_ce')))
  gradient_rows.extend(dict(public_steps=steps,**g) for g in result['gradients'])
 for filename,data in (('checkpoints.csv',rows),('stages.csv',stage_rows),('gradients.csv',gradient_rows)):
  with (out/filename).open('w',newline='',encoding='utf-8') as f:
   writer=csv.DictWriter(f,fieldnames=list(data[0]));writer.writeheader();writer.writerows(data)
 import matplotlib
 matplotlib.use('Agg')
 from matplotlib import pyplot as plt
 n=len(next(iter(results.values()))['metrics'][0]['clients'])
 fig,axes=plt.subplots(n,1,figsize=(9,2*n),sharex=True,squeeze=False)
 for c in range(n):
  ax=axes[c,0]
  for steps in results:
   data=[r for r in stage_rows if r['public_steps']==steps and r['client']==c and r['phase']=='after_public' and r['split']=='public']
   ax.plot([r['round'] for r in data],[r['largest_cluster_fraction'] for r in data],label=f'{steps} public steps')
  ax.set_ylim(0,1.02);ax.set_ylabel(f'Client {c}');ax.axhline(.99,color='gray',linestyle=':',linewidth=.8)
 axes[0,0].set_title('Public budget intervention: fixed public probe concentration');axes[0,0].legend()
 axes[-1,0].set_xlabel('Round');fig.tight_layout();fig.savefig(out/'public_concentration.svg');plt.close(fig)
 lines=['# 公共更新步数干预','','仅改变公共SGD步数；原始完整教师关系图、聚合、私有更新和学习率保持不变。诊断开销包含额外观察，不作认证省时测量。','','|公共步数|轮次|ACC|单簇客户端|最大簇≥99%客户端|','|---:|---:|---:|---:|---:|']
 for r in rows:lines.append(f"|{r['public_steps']}|{r['round']}|{r['acc']:.6f}|{r['single_cluster_clients']}|{r['dominant_99_clients']}|")
 lines+=['','先看逐客户端是否避免塌缩、私有伪标签拟合是否恢复，再看ACC/NMI/ARI。降低预算的计算减少不能计作认证收益；此轮不替代B/E/D性能对照。','']
 (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')

def main():
 if not __debug__:raise RuntimeError('Python -O is unsupported')
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--preset',choices=('full','smoke'),default='full');parser.add_argument('--source-results',type=Path);parser.add_argument('--output',type=Path)
 a=parser.parse_args();fixture=a.preset=='smoke';rounds=3 if fixture else 40
 source=(a.source_results or ROOT/'experiments/stl10_transfer'/('results_smoke_final' if fixture else 'results_full')).resolve()
 out=(a.output or Path(__file__).parent/f'results_{a.preset}').resolve()
 if out.exists() and any(out.iterdir()):raise FileExistsError('Choose a new --output; existing results are not overwritten')
 print('Checking frozen source and existing cache...',flush=True)
 env=json.loads((source/'environment.json').read_text(encoding='utf-8'));check_environment(env)
 if env['fixture']!=fixture:raise ValueError('Real/fixture identity differs')
 original=max((spec_from_json(s) for s in env['plan']),key=lambda s:s.config.samples)
 specs=[replace(original,steps=s) for s in budgets(a.preset)]
 for spec in specs:spec.validate()
 marker=json.loads((source/'prepared_iid_seed_1001.json').read_text(encoding='utf-8'));prepared=Path(marker['path'])
 if digest(prepared/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Cache changed')
 verify(prepared,original.config,1001,'iid',fixture=fixture)
 anchor_path=source/'runs'/f'iid_{original.case_id}_seed_1001_B.json'
 anchor=json.loads(anchor_path.read_text(encoding='utf-8'))
 check_run(anchor,dict(seed=1001,partition='iid',method='B',case_id=original.case_id),original,prepared,fixture)
 frozen=sources();out.mkdir(parents=True,exist_ok=True)
 write(out/'environment.json',dict(preset=a.preset,seed=1001,partition='iid',rounds=rounds,specs=[s.json() for s in specs],source_results=str(source),source_hashes=frozen,cache_metadata_sha256=marker['metadata_sha256'],anchor_sha256=digest(anchor_path),started_utc=time.time()))
 with threadpool_limits(limits=1):
  data=Prepared(prepared,original.config,allow_test_fixture=True)
  try:
   results={}
   for spec in specs:
    print(f'Public steps={spec.steps}; private budget unchanged',flush=True)
    result,_=drive(data,spec,'J',rounds,progress=True)
    result.update(spec=spec.json(),public_steps=spec.steps)
    validate(result,spec,rounds)
    if spec.steps==original.steps:compare_anchor(result,anchor)
    results[spec.steps]=result;write(out/f'public_steps_{spec.steps}.json',seal(result))
   assert len({r['initial_head_digest'] for r in results.values()})==1
   base=next(iter(results.values()))
   for result in results.values():
    for r,b in zip(result['round_records'],base['round_records']):
     for key in ('private_subset_digest','private_samples_per_client','private_subset_pseudo_histograms','private_optimizer_steps','private_forward_endpoints'):
      assert r[key]==b[key],f'Private workload changed: {key}'
   reports(out,results)
  finally:data.close()
 check_environment(env)
 if sources()!=frozen:raise ValueError('Diagnostic code changed during run')
 write(out/'completed.json',dict(public_budgets=list(budgets(a.preset)),runs=len(results),rounds=rounds,original_budget_anchor=original.steps,anchor_rounds_matched=rounds,private_workload_identical=True,files={p.name:digest(p) for p in out.iterdir() if p.is_file()},ended_utc=time.time()))
 print('Finished: '+str(out/'report.md'),flush=True)
if __name__=='__main__':main()
