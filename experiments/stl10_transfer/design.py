from dataclasses import replace
from experiments.public_scaling.config import preset
from experiments.private_workload.design import Spec,spec_from_json
SEEDS=(1001,1002,1003)
PARTITIONS=('iid','dirichlet_0.1')
METHODS=('B','E','D')
def plan(name,device=None):
 c=replace(preset(name),prepare_device=device or ('cuda' if name=='full' else 'cpu'))
 if name=='full':
  c=replace(c,train_limit=16384+5000,test_limit=8000,samples=16384)
  specs=[Spec(replace(c,samples=m),'fixed',8,None) for m in (4096,16384)]
 else:
  c=replace(c,public_pool=128,train_limit=128+256,test_limit=64,samples=128,dimensions=(32,64),pretrain_epochs=1,rounds=3,eval_every=1)
  specs=[Spec(replace(c,samples=m),'fixed',1,None) for m in (32,128)]
 for s in specs:s.validate()
 return specs
def schedule(name):
 out=[];i=0
 for seed in (SEEDS if name=='full' else (1001,)):
  for part in PARTITIONS:
   for s in plan(name):
    order=METHODS[i%3:]+METHODS[:i%3]
    for pos,m in enumerate(order):out.append(dict(seed=seed,partition=part,case_id=s.case_id,method=m,repeat=0,triple=i,position=pos))
    i+=1
 return out
def filename(meta):return f"{meta['partition']}_{meta['case_id']}_seed_{meta['seed']}_{meta['method']}.json"
