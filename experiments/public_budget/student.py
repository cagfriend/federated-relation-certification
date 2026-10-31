"""Same original BCE/SGD, optionally truncate the original shuffled edge order."""
import hashlib
import numpy as np
from experiments.public_scaling.head import relation_loss_grad

def selected_edges(spec,seed,client,rnd):
    c=spec.config;e=c.samples*c.degree//2
    order=np.random.default_rng(np.random.SeedSequence([seed,402,client,rnd,0])).permutation(e)
    return order if spec.policy=='full' else order[:spec.steps*c.public_edge_batch]

def update(head,features,edges,targets,spec,seed,client,rnd):
    c=spec.config;order=selected_edges(spec,seed,client,rnd)
    loss_sum=0.;edge_count=endpoints=0
    for offset in range(0,len(order),c.public_edge_batch):
        ids=order[offset:offset+c.public_edge_batch]
        vertices,inverse=np.unique(edges[ids].ravel(),return_inverse=True)
        loss,dw,db=relation_loss_grad(features[vertices],inverse.reshape(-1,2),targets[ids],head.w,head.b)
        head.apply(dw,db,c.head_lr*c.public_weight)
        loss_sum+=loss*len(ids);edge_count+=len(ids);endpoints+=len(vertices)
    return loss_sum/edge_count,endpoints,order

def schedule_digest(orders):
    h=hashlib.sha256()
    for order in orders:h.update(order.astype('<u4').tobytes())
    return h.hexdigest()

class Coverage:
    """Case-level observer outside method timing and persistent method bytes."""
    def __init__(self,n,edges,samples):
        self.edges=edges;self.seen=np.zeros((n,len(edges)),bool);self.points=np.zeros((n,samples),bool)
    def observe(self,orders):
        for c,ids in enumerate(orders):self.seen[c,ids]=True;self.points[c,self.edges[ids].ravel()]=True
        return self.snapshot()
    def snapshot(self):
        return dict(mean_client_edge_fraction=float(self.seen.mean()),
            min_client_edge_fraction=float(self.seen.mean(axis=1).min()),
            mean_client_endpoint_fraction=float(self.points.mean()))
