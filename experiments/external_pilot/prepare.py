import copy
import hashlib
import json
import time
from pathlib import Path
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F
from experiments.quantity_heterogeneity.partition import partition_indices
from experiments.quantity_heterogeneity.data import resize_area32,read_labels
from .common import SSLModel,batches,model_digest

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.part');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8');temp.replace(path)
def read(path):return json.loads(Path(path).read_bytes())

def selected_images(path,ids):
    raw=np.memmap(path,dtype=np.uint8,mode='r').reshape(-1,3,96,96)
    return torch.from_numpy(resize_area32(raw.transpose(0,1,3,2)[ids]))

def prepare(root,data_dir,cfg):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    for partition in cfg['partitions']:
        out=root/partition;marker=out/'manifest.json'
        if marker.exists():
            meta=read(marker)
            if meta['config']!=cfg:raise ValueError('Preparation configuration changed')
            expected_source='synthetic only' if cfg['preset']=='smoke' else str(Path(data_dir).resolve())
            if meta['source']!=expected_source:raise ValueError('Preparation data source changed')
            for name,h in meta['files'].items():
                if sha(out/name)!=h:raise ValueError('Preparation digest mismatch')
            continue
        if out.exists() and any(out.iterdir()):raise ValueError('Incomplete preparation; choose a new output/cache')
        out.mkdir(parents=True,exist_ok=True);start=time.perf_counter()
        n=sum(cfg['capacities']);rng=np.random.default_rng(cfg['seed'])
        if cfg['preset']=='smoke':
            labels=np.arange(n)%10
            base=torch.from_numpy(rng.uniform(0,1,(10,3072)).astype('float32'))
            train=(base[torch.from_numpy(labels)]+torch.from_numpy(rng.normal(0,.02,(n,3072)).astype('float32'))).clamp(0,1)
            public=base[torch.arange(cfg['public_size'])%10].clone()
            test=base[torch.arange(cfg['test_size'])%10].clone();truth=np.arange(cfg['test_size'])%10
            public_ids=np.arange(cfg['public_size']);test_ids=np.arange(cfg['test_size']);source='synthetic only'
        else:
            data_dir=Path(data_dir)
            labels=read_labels(data_dir/'train_y.bin')[:n]
            train=selected_images(data_dir/'train_X.bin',np.arange(n))
            count=(data_dir/'unlabeled_X.bin').stat().st_size//(3*96*96)
            public_ids=np.random.default_rng(np.random.SeedSequence([cfg['seed'],510])).permutation(count)[:cfg['public_size']]
            public=selected_images(data_dir/'unlabeled_X.bin',public_ids)
            test_count=(data_dir/'test_X.bin').stat().st_size//(3*96*96)
            test_ids=np.random.default_rng(np.random.SeedSequence([cfg['seed'],511])).permutation(test_count)[:cfg['test_size']]
            test=selected_images(data_dir/'test_X.bin',test_ids);truth=read_labels(data_dir/'test_y.bin')[test_ids]
            source=str(data_dir.resolve())
        _,ids,diagnostics=partition_indices(labels,0,6,cfg['seed'],partition,cfg['capacities'])
        private=[train[idx].clone() for idx in ids]
        data_seconds=time.perf_counter()-start
        models=[];warm_start=time.perf_counter()
        for c,width in enumerate(cfg['widths']):
            torch.manual_seed(cfg['seed']+220+c)
            model=SSLModel(width);decoder=nn.Linear(width,3072)
            opt=torch.optim.Adam(list(model.encoder.parameters())+list(decoder.parameters()),lr=cfg['ae_lr'])
            for epoch in range(cfg['ae_epochs']):
                for idx in batches(len(private[c]),cfg['local_batch'],cfg['seed']+c*101+epoch):
                    x=private[c][idx];opt.zero_grad();prediction=torch.sigmoid(decoder(F.relu(model.encoder.linear(x))))
                    loss=F.mse_loss(prediction,x);loss.backward();opt.step()
            models.append(model)
        warm_seconds=time.perf_counter()-warm_start
        torch.save(dict(private=private,public=public,private_ids=[torch.from_numpy(x) for x in ids],public_ids=torch.from_numpy(public_ids)),out/'train.pt')
        torch.save(dict(test=test,truth=torch.from_numpy(np.asarray(truth)),test_ids=torch.from_numpy(test_ids)),out/'evaluation.pt')
        torch.save([m.state_dict() for m in models],out/'initial.pt')
        write(marker,dict(config=cfg,partition=partition,source=source,partition_diagnostics=diagnostics,
            initial_model_digest=model_digest(models),common_ae_seconds=warm_seconds,
            preparation_seconds=time.perf_counter()-start,data_preparation_seconds=data_seconds,
            save_and_manifest_seconds=time.perf_counter()-start-data_seconds-warm_seconds,files={p.name:sha(p) for p in out.glob('*.pt')},
            labels_usage='labels used only for partition construction and held-out scoring; never supplied to training methods'))

def load(root,partition,cfg):
    path=Path(root)/partition;meta=read(path/'manifest.json')
    if meta['config']!=cfg:raise ValueError('Cache config mismatch')
    for name,h in meta['files'].items():
        if sha(path/name)!=h:raise ValueError('Cache modified')
    train=torch.load(path/'train.pt',weights_only=True)
    initial=torch.load(path/'initial.pt',weights_only=True)
    models=[SSLModel(w) for w in cfg['widths']]
    for m,state in zip(models,initial):m.load_state_dict(state)
    if model_digest(models)!=meta['initial_model_digest']:raise ValueError('Different initialization')
    return models,train,meta
