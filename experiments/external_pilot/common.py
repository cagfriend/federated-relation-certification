import copy
import hashlib
import io
import json
import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

class Encoder(nn.Module):
    def __init__(self,width,input_dim=3072):
        super().__init__();self.linear=nn.Linear(input_dim,width);self.width=width
    def forward(self,x):return F.normalize(F.relu(self.linear(x)),dim=1,eps=1e-12)

class SSLModel(nn.Module):
    def __init__(self,width):
        super().__init__();self.encoder=Encoder(width)
        self.projector=nn.Sequential(nn.Linear(width,64),nn.ReLU(),nn.Linear(64,32))
        self.predictor=nn.Sequential(nn.Linear(32,32),nn.ReLU(),nn.Linear(32,32))
    def encode(self,x):return self.encoder(x)
    def forward(self,x):return self.projector(self.encode(x))

def batches(n,batch,seed):
    ids=np.random.default_rng(seed).permutation(n)
    chunks=[ids[i:i+batch] for i in range(0,n,batch)]
    # SSL denominators need >=2 items. Merge a singleton into the prior batch.
    if len(chunks)>1 and len(chunks[-1])==1:chunks[-2]=np.concatenate(chunks[-2:]);chunks.pop()
    return chunks

def augment(x,seed):
    g=torch.Generator(device=x.device).manual_seed(int(seed))
    images=x.reshape(-1,3,32,32)
    # Shared modest image augmentation; both views are independently sampled.
    padded=F.pad(images,(4,4,4,4),mode='reflect')
    offsets=torch.randint(0,9,(len(x),2),generator=g,device=x.device)
    crops=torch.stack([padded[i,:,int(a):int(a)+32,int(b):int(b)+32] for i,(a,b) in enumerate(offsets)])
    flip=torch.rand((len(x),1,1,1),generator=g,device=x.device)<.5
    crops=torch.where(flip,crops.flip(-1),crops)
    brightness=.8+.4*torch.rand((len(x),1,1,1),generator=g,device=x.device)
    noise=.02*torch.randn(crops.shape,generator=g,device=x.device)
    return (crops*brightness+noise).clamp(0,1).reshape(len(x),-1)

def simsiam_loss(model,a,b):
    za,zb=model(a),model(b)
    pa,pb=model.predictor(za),model.predictor(zb)
    return -.5*(F.cosine_similarity(pa,zb.detach(),dim=1).mean()+F.cosine_similarity(pb,za.detach(),dim=1).mean())

def nt_xent(a,b,temp=.4):
    z=F.normalize(torch.cat([a,b]),dim=1);n=len(a)
    logits=z@z.T/temp;logits=logits.masked_fill(torch.eye(2*n,dtype=torch.bool,device=z.device),float('-inf'))
    targets=(torch.arange(2*n,device=z.device)+n)%(2*n)
    return F.cross_entropy(logits,targets)

def model_digest(models):
    h=hashlib.sha256()
    for model in models:
        for name,t in model.state_dict().items():h.update(name.encode());h.update(t.detach().cpu().numpy().tobytes())
    return h.hexdigest()

class Wire:
    """Actual serialization roundtrip; payload+JSON envelope, no sockets.

    Coordinator is client0. Local work is counted in elapsed time but not bytes.
    Values are bytes of the chosen encoding, not theoretical parameter counts.
    """
    def __init__(self):self.total=0;self.up=0;self.down=0;self.messages=0;self.events=[]
    def _roundtrip(self,value,src,dst,tag):
        if src==dst:return copy.deepcopy(value)
        stream=io.BytesIO();torch.save(value,stream);payload=stream.getvalue()
        envelope=json.dumps(dict(src=src,dst=dst,tag=tag,length=len(payload)),sort_keys=True).encode()
        packet=len(envelope).to_bytes(4,'little')+envelope+payload
        n=int.from_bytes(packet[:4],'little');meta=json.loads(packet[4:4+n]);body=packet[4+n:]
        if meta['length']!=len(body):raise ValueError('Truncated transfer')
        received=torch.load(io.BytesIO(body),map_location='cpu',weights_only=True)
        self.total+=len(packet);self.up+=len(packet) if dst==0 else 0;self.down+=len(packet) if dst!=0 else 0
        self.messages+=1;self.events.append(dict(tag=tag,src=src,dst=dst,bytes=len(packet)))
        return received
    def tensor(self,value,src,dst,tag):
        return self._roundtrip(value.detach().cpu(),src,dst,tag).to(value.device)
    def state(self,value,src,dst,tag):
        return self._roundtrip({k:v.detach().cpu() for k,v in value.items()},src,dst,tag)
    def snapshot(self):return dict(total_bytes=self.total,up_bytes=self.up,down_bytes=self.down,messages=self.messages)
