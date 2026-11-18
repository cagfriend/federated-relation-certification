METHODS=('Ours','Hetero-SSFL','FLESD','FedMKD')
def config(preset):
    if preset not in ('pilot','smoke'):raise ValueError(preset)
    smoke=preset=='smoke'
    return dict(preset=preset,seed=1201,rounds=2 if smoke else 200,
        widths=[64]*3+[128]*3 if smoke else [128]*3+[256]*3,
        capacities=[20,30,40]*2 if smoke else [100,200,300]*2,
        public_size=32 if smoke else 512,test_size=40 if smoke else 1000,
        local_batch=16 if smoke else 64,public_batch=16 if smoke else 64,
        public_steps=2,lr=.001,alignment_weight=1.0,global_width=128 if smoke else 256,
        classes=10,ae_epochs=1,ae_lr=.001,head_lr=.1,
        private_batch=128,relation_batch=16 if smoke else 64,
        public_weights=[.125,.5,.5,.125,.5,.5],eval_every=10,
        device='cpu',threads=1,partitions=['iid'] if smoke else ['iid','dirichlet_0.1'])

def schedule(cfg):
    return [dict(partition=p,method=m,seed=cfg['seed']) for i,p in enumerate(cfg['partitions'])
            for m in (METHODS[i:]+METHODS[:i])]
