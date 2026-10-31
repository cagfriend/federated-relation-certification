"""Exact counterfactual targets and replayable relation diagnostics."""
import base64
import hashlib
import numpy as np

NAMES=('Local','Self','Aggregate','Shuffled')
TARGETS=NAMES[1:]

def digest(*arrays):
    h=hashlib.sha256()
    for a in arrays:h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()

def permutation(edges,seed,rnd):
    p=np.random.default_rng(np.random.SeedSequence([seed,906,rnd])).permutation(edges)
    if edges>1 and np.array_equal(p,np.arange(edges)):p=np.roll(p,1)
    return p

def target_matrix(relations,kind,seed,rnd):
    r=np.asarray(relations,dtype=np.uint8)
    if r.ndim!=2 or len(r)<2 or not r.shape[1] or np.any(r>1):raise ValueError('Invalid hard relations')
    if kind=='Self':return r.astype(np.float64)
    counts=r.sum(axis=0,dtype=np.int64)
    if kind=='Shuffled':counts=counts[permutation(r.shape[1],seed,rnd)]
    elif kind!='Aggregate':raise ValueError('Invalid public target kind')
    return np.broadcast_to(counts.astype(np.float64)/len(r),r.shape).copy()

def relation_record(relations,kind,seed,rnd,truth=None):
    r=np.asarray(relations,dtype=np.uint8);n,e=r.shape
    t=target_matrix(r,kind,seed,rnd);counts=r.sum(axis=0,dtype=np.int64)
    shuffled=counts[permutation(e,seed,rnd)]
    hist=np.bincount(np.rint(t*n).astype(int).ravel(),minlength=n+1)
    record=dict(round=rnd,method=kind,clients=n,edges=e,
        relation_bits_b64=[base64.b64encode(np.packbits(row,bitorder='little').tobytes()).decode('ascii') for row in r],
        input_relations_digest=digest(r),raw_counts_digest=digest(counts.astype('<u8')),
        permutation_digest=digest(permutation(e,seed,rnd).astype('<u4')),
        applied_targets_digest=digest(t.astype('<f8')),
        target_mean=float(t.mean()),target_std=float(t.std()),
        target_value_histogram=hist.tolist(),
        target_differs_from_self_fraction=float(np.mean(t!=r)),
        mean_abs_target_minus_self=float(np.mean(np.abs(t-r))),
        mean_other_clients_opposite_fraction=float(np.mean(np.abs((counts[None,:]-r)/(n-1)-r))),
        pairwise_client_relation_disagreement=float(np.mean(2*counts*(n-counts)/(n*(n-1)))),
        shuffled_changed_edge_fraction=float(np.mean(counts!=shuffled)),
        public_truth_brier=None,public_truth_target_gap=None,public_truth_same_fraction=None,
        public_truth_positive_brier=None,public_truth_negative_brier=None,public_truth_constant_prior_brier=None)
    if truth is not None:
        truth=np.asarray(truth,dtype=np.float64)
        if truth.shape!=(e,) or np.any((truth!=0)&(truth!=1)):raise ValueError('Invalid offline relation truth')
        record['public_truth_brier']=float(np.mean((t-truth)**2))
        record['public_truth_same_fraction']=float(truth.mean())
        record['public_truth_constant_prior_brier']=float(np.mean((truth.mean()-truth)**2))
        if np.any(truth==1):record['public_truth_positive_brier']=float(np.mean((t[:,truth==1]-1)**2))
        if np.any(truth==0):record['public_truth_negative_brier']=float(np.mean(t[:,truth==0]**2))
        if np.any(truth==1) and np.any(truth==0):
            record['public_truth_target_gap']=float(t[:,truth==1].mean()-t[:,truth==0].mean())
    return record

def validate_record(record,seed,truth=None):
    e=record['edges'];rows=[]
    if e<1 or record['clients']<2 or len(record['relation_bits_b64'])!=record['clients']:raise ValueError('Invalid relation log shape')
    for value in record['relation_bits_b64']:
        raw=base64.b64decode(value,validate=True)
        if len(raw)!=(e+7)//8:raise ValueError('Invalid packed relation length')
        row=np.unpackbits(np.frombuffer(raw,dtype=np.uint8),bitorder='little')
        if np.any(row[e:]):raise ValueError('Nonzero relation padding')
        rows.append(row[:e])
    rebuilt=relation_record(np.array(rows),record['method'],seed,record['round'],truth)
    for key,value in rebuilt.items():
        if truth is None and key.startswith('public_truth_'):continue
        if record.get(key)!=value:raise ValueError('Relation log mismatch: '+key)
    return target_matrix(np.array(rows),record['method'],seed,record['round'])
