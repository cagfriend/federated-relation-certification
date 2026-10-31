from dataclasses import dataclass,replace
from experiments.public_scaling.config import preset,from_json

PARTITIONS=('iid','dirichlet_0.1')
SEEDS=(404,505,606)
METHODS=('B','E','D')
QUALITY_ACC_DROP=0.01

@dataclass(frozen=True)
class Spec:
    config:object
    policy:str='full'
    steps:int|None=None

    @property
    def case_id(self):return f'm{self.config.samples}_'+('full' if self.policy=='full' else f'fixed{self.steps}')
    @property
    def effective_steps(self):
        return (self.config.samples*self.config.degree//2+self.config.public_edge_batch-1)//self.config.public_edge_batch if self.policy=='full' else self.steps
    def validate(self):
        c=self.config;c.validate()
        if c.public_epochs!=1:raise ValueError('This experiment fixes one public epoch')
        if self.policy not in ('full','fixed'):raise ValueError('Unknown public budget policy')
        if self.policy=='full' and self.steps is not None:raise ValueError('Full traversal cannot request fixed steps')
        if self.policy=='fixed' and (type(self.steps)!=int or self.steps<1 or self.steps*c.public_edge_batch>c.samples*c.degree//2):
            raise ValueError('Fixed budget must fit distinct graph edges')
    def json(self):return dict(config=self.config.json(),policy=self.policy,steps=self.steps)

def spec_from_json(v):
    s=Spec(from_json(v['config']),v['policy'],v['steps']);s.validate();return s

def plan(name,device=None):
    base=replace(preset(name),prepare_device=device or ('cuda' if name=='full' else 'cpu'))
    small=base.public_pool//4
    steps=(small*base.degree//2+base.public_edge_batch-1)//base.public_edge_batch
    specs=[Spec(replace(base,samples=small)),Spec(replace(base,samples=base.public_pool)),Spec(replace(base,samples=base.public_pool),'fixed',steps)]
    for s in specs:s.validate()
    if len({str(s.config.preparation()) for s in specs})!=1:raise AssertionError('Preparation changed across budgets')
    return specs
