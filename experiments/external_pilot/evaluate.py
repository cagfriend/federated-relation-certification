"""Observers never pass labels to a training algorithm; excluded from timers."""
import numpy as np
import torch
from sklearn.cluster import KMeans
from sklearn.metrics import normalized_mutual_info_score,adjusted_rand_score
from scipy.optimize import linear_sum_assignment

def scores(y,p,k):
    table=np.zeros((k,k),dtype=np.int64)
    np.add.at(table,(y,p),1)
    a,b=linear_sum_assignment(-table)
    counts=np.bincount(p,minlength=k)
    return dict(acc=float(table[a,b].sum()/len(y)),nmi=float(normalized_mutual_info_score(y,p)),
        ari=float(adjusted_rand_score(y,p)),occupied=int(np.count_nonzero(counts)),
        empty=int(k-np.count_nonzero(counts)),largest=float(counts.max()/len(y)),
        cluster_counts=counts.astype(int).tolist(),
        cluster_proportions=(counts/len(y)).astype(float).tolist())

@torch.no_grad()
def evaluate(algorithm,private,evaluation,cfg):
    test=algorithm.representations(evaluation['test']);truth=evaluation['truth'].numpy()
    records=[]
    for c,x in enumerate(private):
        features=algorithm.representations(x)[c].cpu().numpy()
        km=KMeans(n_clusters=cfg['classes'],n_init=3,max_iter=100,random_state=cfg['seed']+c).fit(features)
        pred=km.predict(test[c].cpu().numpy())
        row=dict(client=c,**scores(truth,pred,cfg['classes']))
        if hasattr(algorithm,'heads'):
            row['native_head']=scores(truth,test[c].numpy().argmax(1),cfg['classes'])
        records.append(row)
    return dict(clients=records,mean={k:float(np.mean([r[k] for r in records])) for k in ('acc','nmi','ari','occupied','empty','largest')})
