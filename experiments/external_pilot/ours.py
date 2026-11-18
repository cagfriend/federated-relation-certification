"""Original frozen-feature CE/BCE and exact relation certificate, small scale."""
import hashlib
import time
from types import SimpleNamespace
import numpy as np
import torch
from sklearn.cluster import KMeans
from experiments.public_scaling.head import Head,probabilities
from experiments.private_prior.training import private_workload_epoch
from experiments.public_budget.student import update
from experiments.public_scaling.certification import RelationGenerator,hard_relations,make_matching
from experiments.public_scaling.protocol import RelationProtocol

class Ours:
    def __init__(self,models,config,wire,private,public,*,initialization='random',diagnostic_callback=None):
        if initialization not in ('random','centers'):raise ValueError(initialization)
        self.diagnostic_callback=diagnostic_callback
        self.models=models;self.cfg=config;self.heads=[];self.generators=[]
        for m in models:m.eval().requires_grad_(False)
        feature_start=time.perf_counter()
        with torch.no_grad():
            self.private=[m.encode(x).double().numpy() for m,x in zip(models,private)]
            self.public=[m.encode(public).double().numpy() for m in models]
        self.feature_extraction_seconds=time.perf_counter()-feature_start
        self.pseudo=[];self.centers=[];self.initialization_seconds=0.
        for c,z in enumerate(self.private):
            km=KMeans(n_clusters=config['classes'],n_init=3,max_iter=100,random_state=config['seed']+101*c)
            self.pseudo.append(km.fit_predict(z));self.centers.append(km.cluster_centers_.copy())
            self.heads.append(Head(z.shape[1],config['classes'],config['seed'],c))
            if initialization=='centers':
                conversion_start=time.perf_counter()
                self.heads[-1].w=2*self.centers[-1].copy()
                self.heads[-1].b=-np.sum(self.centers[-1]**2,axis=1)
                self.initialization_seconds+=time.perf_counter()-conversion_start
        self.edges=make_matching(len(public),config['seed'])
        self.protocol=RelationProtocol(self.edges,len(public),config['classes'],tuple(config['widths']),adaptive=True)
        self.config=SimpleNamespace(classes=config['classes'],private_epochs=1,private_batch=config['private_batch'],
            head_lr=config['head_lr'],samples=len(public),degree=1,public_edge_batch=config['relation_batch'],public_weight=.5)
        self.stats={};self.last_snapshot=None

    def round(self,private,public,seed,rnd):
        if self.diagnostic_callback:self.diagnostic_callback(self,rnd,'T0')
        start=time.perf_counter();losses=[]
        for c,head in enumerate(self.heads):
            loss,_,_=private_workload_epoch(head,self.private[c],self.pseudo[c],self.config,seed,c,rnd,None);losses.append(loss)
        private_s=time.perf_counter()-start
        if self.diagnostic_callback:self.diagnostic_callback(self,rnd,'T1')
        t=time.perf_counter();relations=[];points=0;certified=0
        self.last_snapshot=[(h.w.copy(),h.b.copy()) for h in self.heads]
        for c,(w,b) in enumerate(self.last_snapshot):
            if rnd==1:
                g=RelationGenerator(self.public[c],w,b,self.edges,'relation');self.generators.append(g)
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
            public_seconds=public_s,teacher_endpoints=points,certified_edges=certified)

    def audit(self):
        comparisons=0
        for z,(w,b),rel in zip(self.public,self.last_snapshot,self.last_relations):
            expected=hard_relations((z@w.T+b).argmax(1),self.edges)
            if not np.array_equal(rel,expected):raise ValueError('Incorrect relation certification')
            comparisons+=len(rel)
        return comparisons

    def representations(self,x):
        with torch.no_grad():
            return [torch.from_numpy(probabilities(m.encode(x).double().numpy(),h.w,h.b)) for m,h in zip(self.models,self.heads)]

    def state_digest(self):
        h=hashlib.sha256()
        for head in self.heads:h.update(head.w.tobytes());h.update(head.b.tobytes())
        return h.hexdigest()

    def traffic(self):return self.protocol.traffic.snapshot()
