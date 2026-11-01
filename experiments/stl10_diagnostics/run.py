"""STL-10 collapse diagnosis. No encoder fitting and no performance claims."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.stl10_transfer.run import check_environment, check_run, digest, seal
from experiments.stl10_transfer.data import verify
from experiments.private_workload.design import spec_from_json
import experiments.private_workload.engine as original
from experiments.public_scaling.data import Prepared
from experiments.public_scaling.engine import evaluate, heads_digest
from experiments.public_scaling.head import probabilities
from .probes import probe, initial_inspection, gradient_probe, fixed_public_indices, feature_probe

ROOT=Path(__file__).resolve().parents[2]
CHECKPOINTS=(0,1,2,5,10,20,40)
GRADIENT_ROUNDS=(1,2,5,10,20,40)

def write(path,obj):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 temp=path.with_suffix(path.suffix+'.part')
 temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temp.replace(path)

def target_digest(t):return hashlib.sha256(np.asarray(t,dtype='<f8').tobytes()).hexdigest()

@contextmanager
def patched(private,public):
 old_private,old_public=original.private_workload_epoch,original.update
 original.private_workload_epoch,original.update=private,public
 try:yield old_private,old_public
 finally:original.private_workload_epoch,original.update=old_private,old_public

def drive(data,spec,arm,rounds,*,observations=True,frozen_targets=None,progress=False):
 if arm not in ('P','J','F'):raise ValueError('Unknown arm')
 cfg=spec.config;model=original.WorkloadMethod('B',data,spec)
 initial=heads_digest(model.heads);records=[];stages=[];gradients=[];metrics=[]
 fixed=[None]*len(model.heads) if frozen_targets is None else [np.array(t,copy=True) for t in frozen_targets]
 previous=[None]*len(model.heads)
 def state(client):
  h=model.heads[client]
  return dict(client=client,private=probe(h,data.private[client],data.pseudo[client]),public=probe(h,data.public[client],indices=fixed_public_indices(cfg,data.seed,client)))
 if observations:metrics.append(dict(round=0,**evaluate(model.heads,data,cfg)))
 old_private,old_public=original.private_workload_epoch,original.update
 for rnd in range(1,rounds+1):
  row_stages={'round':rnd,'before_private':[],'after_private':[],'after_public':[]};target_info=[]
  if observations:row_stages['before_private']=[state(c) for c in range(len(model.heads))]
  def private(h,z,y,config,seed,client,round_number,limit):
   result=old_private(h,z,y,config,seed,client,round_number,limit)
   if observations:row_stages['after_private'].append(state(client))
   return result
  def public(h,z,edges,t,sp,seed,client,round_number):
   if arm=='F' and fixed[client] is None:fixed[client]=np.array(t,copy=True)
   actual=fixed[client] if arm=='F' else t
   values,counts=np.unique(actual,return_counts=True)
   changed=None if previous[client] is None else float(np.mean(actual!=previous[client]))
   previous[client]=np.array(actual,copy=True)
   info=dict(client=client,kind='counterfactual_not_applied' if arm=='P' else ('fixed_round1' if arm=='F' else 'dynamic'),digest=target_digest(actual),mean=float(actual.mean()),values=values.tolist(),counts=counts.tolist(),changed_fraction_from_previous=changed)
   target_info.append(info)
   if observations and rnd in GRADIENT_ROUNDS:
    gradients.append(dict(round=rnd,client=client,stage='after_private_before_public',**gradient_probe(h,data.private[client],data.pseudo[client],z,edges,actual,cfg,seed,client)))
   result=(0.,0,np.empty(0,dtype=np.int64)) if arm=='P' else old_public(h,z,edges,actual,sp,seed,client,round_number)
   if observations:
    ids=np.random.default_rng(np.random.SeedSequence([seed,612,client])).permutation(len(edges))[:min(256,len(edges))]
    vertices,inverse=np.unique(edges[ids].ravel(),return_inverse=True)
    probs=probabilities(z[vertices],h.w,h.b);pairs=inverse.reshape(-1,2)
    predicted=np.einsum('ij,ij->i',probs[pairs[:,0]],probs[pairs[:,1]])
    info['post_update_relation_probe']=dict(edge_count=len(ids),mean_probability=float(predicted.mean()),target_mae=float(np.mean(np.abs(predicted-actual[ids]))),target_mse=float(np.mean((predicted-actual[ids])**2)))
   return result
  with patched(private,public):row,relations,snapshots,orders=model.step(rnd)
  if arm=='P':row['public_optimizer_steps']=0
  row['diagnostic_arm']=arm;row['student_targets']=target_info
  row['teacher_target_role']='counterfactual' if arm in ('P','F') else 'applied'
  records.append(row)
  if observations:
   row_stages['after_public']=[state(c) for c in range(len(model.heads))] if arm!='P' else []
   stages.append(row_stages)
   if rnd in CHECKPOINTS or rnd==rounds:metrics.append(dict(round=rnd,**evaluate(model.heads,data,cfg)))
  if progress:print(f'{arm}: {rnd}/{rounds}',flush=True)
 return dict(arm=arm,initial_head_digest=initial,round_records=records,stages=stages,gradients=gradients,metrics=metrics,final_head_digest=heads_digest(model.heads)),fixed

ANCHOR_KEYS=('head_digest_after_public','public_schedule_digest','public_optimizer_steps','student_forward_endpoints','public_edges_consumed','committed_counts_digest','received_counts_digests','private_loss','public_loss','private_subset_digest','private_samples_per_client','private_subset_pseudo_histograms','private_optimizer_steps','private_forward_endpoints','positive_relation_fraction','traffic')
def compare_anchor(result,anchor):
 assert result['initial_head_digest']==anchor['initial_head_digest'],'Initial state differs'
 for a,b in zip(result['round_records'],anchor['round_records']):
  for k in ANCHOR_KEYS:
   if a[k]!=b[k]:raise AssertionError(f'Frozen J anchor mismatch at round {a["round"]}: {k}')
 assert len(anchor['round_records'])>=len(result['round_records'])
 for q in result['metrics']:
  old=next((x for x in anchor['metrics'] if x['round']==q['round']),None)
  if old is not None:
   assert old['clients']==q['clients'] and old['mean']==q['mean'],'Evaluation mismatch'

def report(output,arms):
 import csv
 stage_rows=[];gradient_rows=[]
 for arm,result in arms.items():
  for rnd in result['stages']:
   for phase in ('before_private','after_private','after_public'):
    for c in rnd[phase]:
     for split in ('private','public'):
      stats=c[split]
      stage_rows.append(dict(arm=arm,round=rnd['round'],phase=phase,client=c['client'],split=split,occupied_clusters=stats['occupied_clusters'],largest_cluster_fraction=stats['largest_cluster_fraction'],mean_confidence=stats['mean_confidence'],pseudo_ce=stats.get('pseudo_ce'),pseudo_accuracy=stats.get('pseudo_accuracy')))
  gradient_rows.extend(dict(arm=arm,**x) for x in result['gradients'])
 for name,rows in (('stages.csv',stage_rows),('gradients.csv',gradient_rows)):
  if rows:
   with (output/name).open('w',newline='',encoding='utf-8') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 import matplotlib
 matplotlib.use('Agg')
 from matplotlib import pyplot as plt
 n=len(next(iter(arms.values()))['metrics'][0]['clients'])
 fig,axes=plt.subplots(n,1,figsize=(9,max(4,2*n)),squeeze=False,sharex=True)
 for c in range(n):
  ax=axes[c,0]
  for arm in ('P','J','F'):
   phase='after_private' if arm=='P' else 'after_public'
   rows=[r for r in stage_rows if r['arm']==arm and r['phase']==phase and r['split']=='public' and r['client']==c]
   ax.plot([r['round'] for r in rows],[r['largest_cluster_fraction'] for r in rows],label=arm)
  ax.set_ylim(0,1.02);ax.set_ylabel(f'Client {c}');ax.axhline(.99,color='gray',linestyle=':',linewidth=.8)
 axes[0,0].legend();axes[0,0].set_title('Largest predicted cluster fraction on fixed public probe')
 axes[-1,0].set_xlabel('Round');fig.tight_layout();fig.savefig(output/'public_cluster_concentration.svg');plt.close(fig)
 lines=['# STL-10退化定位结果','','只作退化定位；不是性能测量。P跳过公共更新；F固定第1轮目标。','','|分支|轮次|平均ACC|单簇客户端数|最大簇≥99%客户端数|','|---|---:|---:|---:|---:|']
 for arm in ('P','J','F'):
  for q in arms[arm]['metrics']:
   cs=q['clients'];lines.append(f'|{arm}|{q["round"]}|{q["mean"]["acc"]:.6f}|{sum(c["occupied_clusters"]==1 for c in cs)}|{sum(c["largest_cluster_fraction"]>=.99 for c in cs)}|')
 lines+=['','分阶段公共探针/私有全集簇占用、固定批次梯度和目标分布见各分支JSON。F改变目标的时效性与分布，不能将J/F差异完全归因于单一反馈机制。','']
 (output/'report.md').write_text('\n'.join(lines),encoding='utf-8')

def main():
 if not __debug__:raise RuntimeError('Optimized Python (-O) is unsupported: validation assertions must remain enabled')
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--preset',choices=('full','smoke'),default='full');p.add_argument('--source-results',type=Path);p.add_argument('--output',type=Path)
 a=p.parse_args();fixture=a.preset=='smoke'
 source=(a.source_results or ROOT/'experiments/stl10_transfer'/('results_smoke_final' if fixture else 'results_full')).resolve()
 out=(a.output or Path(__file__).parent/f'results_{a.preset}').resolve()
 if out.exists() and any(out.iterdir()):raise FileExistsError('Output exists. Choose a new --output; source results are never overwritten.')
 env=json.loads((source/'environment.json').read_text(encoding='utf-8'));check_environment(env)
 if env['fixture']!=fixture:raise ValueError('Real/fixture mismatch')
 spec=max((spec_from_json(s) for s in env['plan']),key=lambda s:s.config.samples);cfg=spec.config
 marker=json.loads((source/'prepared_iid_seed_1001.json').read_text(encoding='utf-8'));prepared=Path(marker['path'])
 if digest(prepared/'prepared.json')!=marker['metadata_sha256']:raise ValueError('Cache metadata changed')
 verify(prepared,cfg,1001,'iid',fixture=fixture)
 anchor_path=source/'runs'/f'iid_{spec.case_id}_seed_1001_B.json'
 anchor=json.loads(anchor_path.read_text(encoding='utf-8'))
 if seal(dict(anchor))['run_sha256']!=anchor['run_sha256']:raise ValueError('Anchor seal changed')
 check_run(anchor,dict(seed=1001,partition='iid',method='B',case_id=spec.case_id),spec,prepared,fixture)
 rounds=3 if fixture else 40
 own={str(x.relative_to(ROOT)):digest(x) for x in Path(__file__).parent.glob('*.py')}
 out.mkdir(parents=True,exist_ok=True)
 identity=dict(preset=a.preset,spec=spec.json(),seed=1001,partition='iid',rounds=rounds,source_results=str(source),source_hashes=env['source_hashes'],diagnostic_sources=own,anchor_sha256=digest(anchor_path),cache_metadata_sha256=marker['metadata_sha256'],started_utc=time.time())
 write(out/'environment.json',identity)
 with threadpool_limits(limits=1):
  data=Prepared(prepared,cfg,allow_test_fixture=True)
  try:
   initial=original.WorkloadMethod('B',data,spec)
   inspection=initial_inspection(data,initial.heads,cfg)
   for c,rec in enumerate(inspection['clients']):
    rec['public_features']=feature_probe(data.public[c]);rec['test_features']=feature_probe(data.test[c])
    rec['pretraining_record']=data.metadata['clients'][c]
   write(out/'initial_inspection.json',inspection)
   arms={}
   for arm in ('P','J','F'):
    arms[arm],fixed=drive(data,spec,arm,rounds,progress=True)
    if arm=='J':compare_anchor(arms[arm],anchor)
    if arm=='F':
     assert arms['J']['round_records'][0]['head_digest_after_public']==arms['F']['round_records'][0]['head_digest_after_public'],'J/F first round differs'
     assert [x['digest'] for x in arms['J']['round_records'][0]['student_targets']]==[target_digest(x) for x in fixed]
     np.save(out/'fixed_round1_targets.npy',np.stack(fixed))
    write(out/f'{arm}.json',seal(arms[arm]))
   report(out,arms)
  finally:data.close()
 check_environment(env)
 assert own=={str(x.relative_to(ROOT)):digest(x) for x in Path(__file__).parent.glob('*.py')},'Diagnostic sources changed'
 write(out/'completed.json',dict(runs=3,rounds=rounds,j_anchor_rounds_matched=rounds,j_f_round1_matched=True,files={str(x.relative_to(out)):digest(x) for x in out.iterdir() if x.is_file()},ended_utc=time.time()))
 print('Finished: '+str(out/'report.md'),flush=True)
if __name__=='__main__':main()
