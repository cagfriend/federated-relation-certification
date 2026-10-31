from dataclasses import dataclass, replace
from experiments.public_scaling.config import preset, from_json

PARTITIONS = ('iid', 'dirichlet_0.1')
SEEDS = (404, 505, 606)
METHODS = ('B', 'E', 'D')
QUALITY_ACC_DROP = 0.01

# Per-client, per-round private SGD caps. None means the original full
# private epoch. The smoke caps are scaled-down analogues that only
# validate the code path; they are not formal evidence.
FORMAL_PRIVATE_LIMITS = (None, 2048, 1024)
SMOKE_PRIVATE_LIMITS = (None, 128, 64)


@dataclass(frozen=True)
class Spec:
    config: object
    policy: str = 'fixed'
    steps: int | None = None
    private_limit: int | None = None

    @property
    def case_id(self):
        limit = 'full' if self.private_limit is None else str(self.private_limit)
        return f'm{self.config.samples}_fixed{self.steps}_priv{limit}'

    @property
    def effective_steps(self):
        return self.steps

    def validate(self):
        c = self.config
        c.validate()
        if c.public_epochs != 1:
            raise ValueError('This experiment fixes one public epoch')
        if self.policy != 'fixed':
            raise ValueError('This experiment fixes the public student budget')
        if type(self.steps) != int or self.steps < 1 or self.steps * c.public_edge_batch > c.samples * c.degree // 2:
            raise ValueError('Fixed budget must fit distinct graph edges')
        if self.private_limit is not None and (type(self.private_limit) != int or self.private_limit < 1):
            raise ValueError('Private limit must be a positive int or None')

    def json(self):
        return dict(config=self.config.json(), policy=self.policy, steps=self.steps,
                    private_limit=self.private_limit)


def spec_from_json(v):
    s = Spec(from_json(v['config']), v['policy'], v['steps'], v['private_limit'])
    s.validate()
    return s


def plan(name, device=None):
    base = replace(preset(name), prepare_device=device or ('cuda' if name == 'full' else 'cpu'))
    small = base.public_pool // 4
    steps = (small * base.degree // 2 + base.public_edge_batch - 1) // base.public_edge_batch
    config = replace(base, samples=base.public_pool)
    limits = FORMAL_PRIVATE_LIMITS if name == 'full' else SMOKE_PRIVATE_LIMITS
    specs = [Spec(config, 'fixed', steps, limit) for limit in limits]
    for s in specs:
        s.validate()
    if len({str(s.config.preparation()) for s in specs}) != 1:
        raise AssertionError('Preparation changed across private workloads')
    return specs
