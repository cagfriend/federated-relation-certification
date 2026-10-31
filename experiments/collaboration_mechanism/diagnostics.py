"""Read-only gradient probes at one post-private student/teacher snapshot."""
import math
import numpy as np
from experiments.public_scaling.head import ce_loss_grad,relation_loss_grad
from .targets import TARGETS,target_matrix,digest

def alignment(private_gradient,public_gradient,weight):
    a=np.concatenate([x.ravel() for x in private_gradient])
    b=np.concatenate([x.ravel() for x in public_gradient])
    na=float(np.linalg.norm(a));nb=float(np.linalg.norm(b));weighted=weight*nb
    cosine=None if na==0 or nb==0 else float(np.clip(np.dot(a,b)/(na*nb),-1,1))
    return dict(private_grad_norm=na,public_grad_norm_raw=nb,
        public_grad_norm_weighted=weighted,weighted_public_private_norm_ratio=None if na==0 else weighted/na,
        gradient_cosine=cosine,gradient_angle_degrees=None if cosine is None else math.degrees(math.acos(cosine)))

def probe(data,config,snapshots,relations,rnd,anchor):
    """Same private/public mini-batches and same w,b for all three target kinds."""
    before=digest(*[a for pair in snapshots for a in pair]);rows=[]
    edge_ids=np.random.default_rng(np.random.SeedSequence([data.seed,902,rnd])).permutation(len(data.edges))[:config.public_edge_batch]
    vertices,inverse=np.unique(data.edges[edge_ids].ravel(),return_inverse=True)
    targets={kind:target_matrix(relations,kind,data.seed,rnd) for kind in TARGETS}
    for client,((w,b),width) in enumerate(zip(snapshots,config.dimensions)):
        ids=np.random.default_rng(np.random.SeedSequence([data.seed,901,client,rnd])).permutation(len(data.private[client]))[:config.private_batch]
        ploss,pw,pb=ce_loss_grad(data.private[client][ids],data.pseudo[client][ids],w,b)
        for kind in TARGETS:
            t=targets[kind][client]
            loss,gw,gb=relation_loss_grad(data.public[client][vertices],inverse.reshape(-1,2),t[edge_ids],w,b)
            row=dict(round=rnd,anchor=anchor,client=client,width=width,target_kind=kind,
                student_snapshot_digest=digest(w,b),private_batch_digest=digest(ids.astype('<u8')),
                public_edge_batch_digest=digest(edge_ids.astype('<u8')),
                private_batch_samples=len(ids),public_batch_edges=len(edge_ids),
                private_loss=ploss,public_loss=loss,public_weight=config.public_weight,
                target_differs_from_self_fraction=float(np.mean(t!=relations[client])),
                mean_abs_target_minus_self=float(np.mean(np.abs(t-relations[client]))),
                **alignment((pw,pb),(gw,gb),config.public_weight))
            if any(not math.isfinite(v) for v in row.values() if isinstance(v,float)):raise ArithmeticError('Nonfinite gradient diagnostic')
            rows.append(row)
    if before!=digest(*[a for pair in snapshots for a in pair]):raise AssertionError('Probe changed snapshots')
    return rows
