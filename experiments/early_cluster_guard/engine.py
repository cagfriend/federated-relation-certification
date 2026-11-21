"""Fixed-pseudolabel, class-balanced multiclass margin guard in private SGD only."""
import time
import numpy as np
from experiments.external_pilot.ours import Ours
from experiments.private_prior.training import private_workload_epoch, CLIENTS, log_prior
from experiments.public_scaling.head import ce_loss_grad
from experiments.public_scaling.generation import make_generator
from experiments.public_budget.student import update
from types import SimpleNamespace

MARGIN = 0.1

def margin_grad(x, labels, w, b, counts, margin=MARGIN):
    """Mean weighted hinge; weights N/(K_nonempty*n_y) from FULL fixed private labels.

    J = mean_i weight[y_i] * max(0, margin + max_{k!=y_i} s_ik - s_i,y_i).
    Equal competitors use the smallest index; exactly zero hinge uses zero gradient.
    """
    logits=x@w.T+b
    competitors=logits.copy();competitors[np.arange(len(labels)),labels]=-np.inf
    rival=competitors.argmax(1)
    gaps=margin+logits[np.arange(len(labels)),rival]-logits[np.arange(len(labels)),labels]
    weights=counts.sum()/(np.count_nonzero(counts)*counts[labels])
    loss=float(np.mean(weights*np.maximum(0,gaps)))
    grad=np.zeros_like(logits)
    factors=weights*(gaps>0)/len(labels)
    grad[np.arange(len(labels)),rival]+=factors
    grad[np.arange(len(labels)),labels]-=factors
    return loss,grad.T@x,grad.sum(0),int(np.count_nonzero(gaps>0))

class GuardedOurs(Ours):
    def __init__(self,*args,strength=0.,until=0,**kwargs):
        super().__init__(*args,**kwargs)
        if strength<0 or until<0:raise ValueError('negative guard setting')
        self.strength=float(strength);self.until=int(until)
        self.counts=[np.bincount(y,minlength=self.cfg['classes']) for y in self.pseudo]
        self.guard_stats=[]

    def private_update(self,head,x,y,conf,seed,client,rnd):
        if self.strength==0 or rnd>self.until:
            self.guard_stats.append(dict(client=client,active=False,hinge_loss=0.,violations=0,examples=0,seconds=0.))
            return private_workload_epoch(head,x,y,conf,seed,client,rnd,None)
        order=np.random.default_rng(np.random.SeedSequence([seed,401,client,rnd,0])).permutation(len(y))
        prior=log_prior(y,conf.classes) if client in CLIENTS else np.zeros(conf.classes)
        total=0.;hinge=0.;violations=0;guard_seconds=0.;gnorm=0.
        # Same batches, RNG, base CE correction and ONE combined SGD step per batch.
        for offset in range(0,len(order),conf.private_batch):
            ids=order[offset:offset+conf.private_batch];xb=x[ids];yb=y[ids]
            loss,dw,db=ce_loss_grad(xb,yb,head.w,head.b+prior)
            start=time.perf_counter()
            penalty,gw,gb,v=margin_grad(xb,yb,head.w,head.b,self.counts[client])
            dw+=self.strength*gw;db+=self.strength*gb
            guard_seconds+=time.perf_counter()-start
            gnorm+=float(np.sqrt(np.sum(gw**2)+np.sum(gb**2)))
            head.apply(dw,db,conf.head_lr)
            total+=loss*len(ids);hinge+=penalty*len(ids);violations+=v
        self.guard_stats.append(dict(client=client,active=True,hinge_loss=hinge/len(y),violations=violations,
            examples=len(y),seconds=guard_seconds,unweighted_gradient_norm_sum=gnorm))
        return total/len(y),len(y),np.arange(len(y))

    def round(self,private,public,seed,rnd):
        if self.diagnostic_callback:self.diagnostic_callback(self,rnd,'T0')
        start=time.perf_counter();losses=[];self.guard_stats=[]
        for c,head in enumerate(self.heads):
            loss,_,_=self.private_update(head,self.private[c],self.pseudo[c],self.config,seed,c,rnd);losses.append(loss)
        private_s=time.perf_counter()-start
        if self.diagnostic_callback:self.diagnostic_callback(self,rnd,'T1')
        t=time.perf_counter();relations=[];points=0;certified=0
        self.last_snapshot=[(h.w.copy(),h.b.copy()) for h in self.heads]
        for c,(w,b) in enumerate(self.last_snapshot):
            if rnd==1:
                g=make_generator(self.public[c],w,b,self.edges,'relation');self.generators.append(g)
                relation=g.initial_relations;del g.initial_relations;points+=len(public)
            else:
                relation,stat=self.generators[c].generate(w,b);points+=stat['forward_endpoints'];certified+=stat['certified_edges_before_refresh']
            relations.append(relation)
        generation_s=time.perf_counter()-t;t=time.perf_counter()
        self.protocol.exchange(relations)
        exchange_s=time.perf_counter()-t;t=time.perf_counter()
        public_losses=[]
        for c,head in enumerate(self.heads):
            conf=SimpleNamespace(**vars(self.config));conf.public_weight=self.cfg['public_weights'][c]
            spec=SimpleNamespace(config=conf,policy='fixed',steps=self.cfg['public_steps'])
            targets=self.protocol.client_counts[c].astype(np.float64)/len(self.heads)
            loss,_,_=update(head,self.public[c],self.edges,targets,spec,seed,c,rnd);public_losses.append(loss)
        self.last_relations=[r.copy() for r in relations]
        public_s=time.perf_counter()-t
        if self.diagnostic_callback:self.diagnostic_callback(self,rnd,'T2')
        return dict(private_loss=float(np.mean(losses)),public_loss=float(np.mean(public_losses)),
            private_seconds=private_s,generation_seconds=generation_s,exchange_seconds=exchange_s,
            public_seconds=public_s,teacher_endpoints=points,certified_edges=certified,guard_active=self.strength>0 and rnd<=self.until,guard_clients=self.guard_stats)

