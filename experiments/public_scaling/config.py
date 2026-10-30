from dataclasses import asdict, dataclass, replace
import math


@dataclass(frozen=True)
class Config:
    dimensions: tuple[int, ...] = (512, 512, 512, 2048, 2048, 2048)
    public_pool: int = 16384
    samples: int = 4096
    degree: int = 1
    classes: int = 10
    rounds: int = 200
    train_limit: int = 60000
    test_limit: int = 10000
    pretrain_epochs: int = 5
    pretrain_batch: int = 256
    pretrain_lr: float = 0.001
    noise_std: float = 0.15
    prepare_device: str = 'cpu'
    prepare_threads: int = 4
    feature_batch: int = 256
    kmeans_restarts: int = 10
    kmeans_max_iter: int = 100
    head_lr: float = 0.1
    private_epochs: int = 1
    private_batch: int = 128
    public_epochs: int = 1
    public_edge_batch: int = 256
    public_weight: float = 1.0
    eval_every: int = 20
    threads: int = 1

    @property
    def case_id(self):
        return f'm{self.samples}_d{self.degree}'

    def validate(self):
        if not 2 <= len(self.dimensions) <= 255 or min(self.dimensions) < 1:
            raise ValueError('Need 2..255 positive model widths')
        if self.public_pool < 32 or self.public_pool % 8 or self.samples < 2 or self.samples % 2 or self.samples > self.public_pool:
            raise ValueError('Need even samples within a public pool divisible by 8, pool>=32')
        if not 1 <= self.degree < self.samples or not 2 <= self.classes <= 64:
            raise ValueError('Invalid degree or K outside 2..64')
        if not self.public_pool + len(self.dimensions) * self.classes <= self.train_limit <= 60000:
            raise ValueError('Insufficient fixed private samples or invalid Fashion-MNIST limit')
        if not 1 <= self.test_limit <= 10000 or self.prepare_device not in ('cpu', 'cuda'):
            raise ValueError('Invalid test limit or preparation device')
        for name in ('rounds', 'pretrain_epochs', 'pretrain_batch', 'prepare_threads', 'feature_batch',
                     'kmeans_restarts', 'kmeans_max_iter', 'private_epochs', 'private_batch',
                     'public_epochs', 'public_edge_batch', 'eval_every', 'threads'):
            if getattr(self, name) < 1:
                raise ValueError(f'{name} must be positive')
        for name in ('pretrain_lr', 'head_lr', 'public_weight'):
            if not math.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be finite and positive')
        if not math.isfinite(self.noise_std) or self.noise_std < 0:
            raise ValueError('noise_std must be finite and nonnegative')

    def json(self):
        result = asdict(self)
        result['dimensions'] = list(self.dimensions)
        return result

    def preparation(self):
        # Crucially NOT samples or degree: all cases share private data/AE/pseudo-labels.
        names = ('dimensions', 'public_pool', 'classes', 'train_limit', 'test_limit', 'pretrain_epochs',
                 'pretrain_batch', 'prepare_threads', 'feature_batch', 'pretrain_lr', 'noise_std',
                 'prepare_device', 'kmeans_restarts', 'kmeans_max_iter', 'threads')
        return {name: self.json()[name] for name in names}


def from_json(value):
    return Config(**{**value, 'dimensions': tuple(value['dimensions'])})


def preset(name):
    if name == 'full':
        return Config()
    if name == 'smoke':
        return Config(dimensions=(32, 64), public_pool=128, samples=32, rounds=3,
                      train_limit=1024, test_limit=128, pretrain_epochs=1, eval_every=1,
                      prepare_threads=1, public_edge_batch=16)
    raise ValueError(name)


def make_plan(base, suite):
    base.validate()
    smallest = base.public_pool // 4
    specs = {'public': [(smallest, 1), (smallest * 2, 1), (base.public_pool, 1)],
             'graph': [(smallest, 1), (smallest, 4), (smallest, 8)],
             'all': [(smallest, 1), (smallest * 2, 1), (base.public_pool, 1), (smallest, 4), (smallest, 8)]}
    if suite not in specs:
        raise ValueError(suite)
    cases = [replace(base, samples=m, degree=d) for m, d in specs[suite]]
    for case in cases:
        case.validate()
    assert all(c.preparation() == base.preparation() for c in cases)
    return cases
