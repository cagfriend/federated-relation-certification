"""FLESD equations 3--10, small heterogeneous architecture adaptation.

Two global students (one per width) retain weights across rounds. Each is
distilled at coordinator0 and distributed to matching-width clients. The
heterogeneous extension is explicit; the original experiments use one width.
"""
import copy
import torch
from torch.nn import functional as F
from .common import augment,batches,nt_xent

def ensemble(similarities,temperature=.1):
    return torch.stack([torch.exp(x/temperature) for x in similarities]).mean(0)

def distill_loss(queries,anchors,targets,temp=.1):
    probabilities=targets/targets.sum(1,keepdim=True).clamp_min(1e-12)
    logq=F.log_softmax(F.normalize(queries,dim=1)@F.normalize(anchors,dim=1).T/temp,dim=1)
    return F.kl_div(logq,probabilities,reduction='batchmean')

class FLESD:
    def __init__(self,models,config,wire):
        self.models=models;self.cfg=config;self.wire=wire;self.global_models={};self.optimizers=[]
        for m in models:
            self.global_models.setdefault(m.encoder.width,copy.deepcopy(m))
            self.optimizers.append(torch.optim.Adam(m.parameters(),lr=config['lr']))
        self.server_optimizers={w:torch.optim.Adam(m.parameters(),lr=config['lr']) for w,m in self.global_models.items()}
        self.momentum={w:copy.deepcopy(m).requires_grad_(False) for w,m in self.global_models.items()}

    def round(self,private,public,seed,rnd):
        local_losses=[]
        for c,(m,opt,x) in enumerate(zip(self.models,self.optimizers,private)):
            for step,ids in enumerate(batches(len(x),self.cfg['local_batch'],seed+1000*rnd+c)):
                a=augment(x[ids],seed+10000*rnd+100*c+2*step);b=augment(x[ids],seed+10000*rnd+100*c+2*step+1)
                opt.zero_grad();loss=nt_xent(m(a),m(b),.4);loss.backward();opt.step();local_losses.append(float(loss.detach()))
        matrices=[]
        with torch.no_grad():
            for c,m in enumerate(self.models):
                reps=m.encode(public);matrices.append(self.wire.tensor(reps@reps.T,c,0,f'flesd_similarity_{rnd}'))
            target=ensemble(matrices)
        losses=[];steps=0
        for width,student in self.global_models.items():
            momentum=self.momentum[width];opt=self.server_optimizers[width]
            qsize=min(128,len(public));queue_ids=torch.arange(qsize)
            with torch.no_grad():queue=momentum.encode(public[queue_ids]).clone()
            offset=0
            orders=batches(len(public),self.cfg['public_batch'],seed+2000*rnd)
            for j in range(self.cfg['public_steps']):
                ids=torch.as_tensor(orders[j%len(orders)])
                with torch.no_grad():
                    for k,v in zip(momentum.parameters(),student.parameters()):k.mul_(.999).add_(v,alpha=.001)
                    keys=momentum.encode(augment(public[ids],seed+3000*rnd+j))
                    for key,idx in zip(keys,ids):queue[offset]=key;queue_ids[offset]=idx;offset=(offset+1)%qsize
                opt.zero_grad();query=student.encode(augment(public[ids],seed+4000*rnd+j))
                loss=distill_loss(query,queue.detach(),target[ids][:,queue_ids]);loss.backward();opt.step()
                losses.append(float(loss.detach()));steps+=1
        for c,m in enumerate(self.models):
            # Local projection heads are retained; the learned encoder is global.
            state=self.wire.state(self.global_models[m.encoder.width].encoder.state_dict(),0,c,f'flesd_encoder_{rnd}')
            m.encoder.load_state_dict(state)
        return dict(local_loss=sum(local_losses)/len(local_losses),server_distillation_loss=sum(losses)/len(losses),
                    local_steps=len(local_losses),server_steps=steps,global_students=len(self.global_models))

    def representations(self,x):
        with torch.no_grad():return [m.encode(x) for m in self.models]
