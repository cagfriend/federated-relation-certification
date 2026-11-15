"""Synthetic multi-cluster features for the smoke pipeline only."""
import numpy as np
from experiments.quantity_heterogeneity import data
from .support import read,write,digest


def prepare(cache,source,spec,seed,partition):
    directory=data.prepare(cache,source,spec,seed,partition,profile='strong',fixture=True)
    metadata=read(directory/'prepared.json')
    if metadata.get('confirmation_synthetic_features')==1:return directory
    if metadata['dataset']!='STL-10 fixture':raise ValueError('Fixture-only features')
    for c,record in enumerate(metadata['clients']):
        rng=np.random.default_rng(np.random.SeedSequence([seed,8761,c]))
        width,count=record['width'],record['private_samples']
        centers=rng.normal(scale=.3,size=(10,width))
        pseudo=np.arange(count,dtype=np.int64)%10
        arrays=dict(pseudo=pseudo,centers=centers,private=centers[pseudo]+rng.normal(scale=.05,size=(count,width)))
        for domain,n in [('public',spec.config.public_pool),('test',spec.config.test_limit)]:
            arrays[domain]=centers[np.arange(n)%10]+rng.normal(scale=.05,size=(n,width))
        for suffix,array in arrays.items():
            path=directory/f'client_{c}_{suffix}.npy';np.save(path,array)
            metadata['files'][path.name]=digest(path)
        record['pseudo_histogram']=np.bincount(pseudo,minlength=10).tolist()
    metadata['confirmation_synthetic_features']=1
    write(directory/'prepared.json',metadata)
    data.verify(directory,spec.config,seed,partition,profile='strong',fixture=True)
    return directory
