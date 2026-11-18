"""Full-duration raw-logit margin guard with fixed all-client private CE priors."""
import time
import numpy as np
from experiments.early_cluster_guard.engine import GuardedOurs, margin_grad
from experiments.private_prior.training import log_prior
from experiments.public_scaling.head import ce_loss_grad


class CorrectedGuardOurs(GuardedOurs):
    def __init__(self, *args, all_clients=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.all_clients = bool(all_clients)
        # Full fixed pseudolabel frequencies, never minibatch/current predictions.
        self.all_log_priors = [log_prior(y, self.cfg['classes']) for y in self.pseudo]

    def private_update(self, head, x, y, conf, seed, client, rnd):
        if not self.all_clients:
            return super().private_update(head, x, y, conf, seed, client, rnd)
        if conf.private_epochs != 1 or conf.private_batch <= 0:
            raise ValueError('This experiment requires one private epoch and positive batch size')
        order = np.random.default_rng(np.random.SeedSequence([seed,401,client,rnd,0])).permutation(len(y))
        prior = self.all_log_priors[client]
        active = self.strength > 0 and rnd <= self.until
        total = hinge = guard_seconds = gnorm = 0.
        violations = 0
        for offset in range(0, len(order), conf.private_batch):
            ids = order[offset:offset+conf.private_batch]
            xb, yb = x[ids], y[ids]
            loss, dw, db = ce_loss_grad(xb, yb, head.w, head.b + prior)
            if active:
                start = time.perf_counter()
                penalty, gw, gb, count = margin_grad(xb, yb, head.w, head.b, self.counts[client])
                dw += self.strength * gw
                db += self.strength * gb
                guard_seconds += time.perf_counter() - start
                gnorm += float(np.sqrt(np.sum(gw**2) + np.sum(gb**2)))
                hinge += penalty * len(ids)
                violations += count
            head.apply(dw, db, conf.head_lr)
            total += loss * len(ids)
        self.guard_stats.append(dict(client=client, active=active, hinge_loss=hinge/len(y),
            violations=violations, examples=len(y) if active else 0, seconds=guard_seconds,
            unweighted_gradient_norm_sum=gnorm))
        return total/len(y), len(y), np.arange(len(y), dtype=np.int64)
