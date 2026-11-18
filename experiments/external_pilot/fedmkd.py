"""Small, explicit FedMKD pilot implementation.

This is a low-cost MLP adaptation of the paper's BYOL local training,
multi-teacher representation attention/distillation, and server-side alignment.
It is not a reproduction of the paper's ResNet/VGG experiments.
"""
from __future__ import annotations

import copy
from contextlib import nullcontext
import math
from typing import Any

import torch
import torch.nn.functional as F

try:  # script and package execution
    from . import common
except ImportError:  # pragma: no cover
    import common  # type: ignore


def _byol_loss(model, target_encoder, target_projector, x, seed):
    a, b = common.augment(x, seed), common.augment(x, seed + 1)
    p_a, p_b = model.predictor(model(a)), model.predictor(model(b))
    with torch.no_grad():
        z_a, z_b = target_projector(target_encoder(a)), target_projector(target_encoder(b))
    return (2 - 2 * F.cosine_similarity(p_a, z_b.detach(), dim=-1)).mean() + (
        2 - 2 * F.cosine_similarity(p_b, z_a.detach(), dim=-1)
    ).mean()


def _ema(target, online, decay: float):
    with torch.no_grad():
        for tp, op in zip(target.parameters(), online.parameters()):
            tp.mul_(decay).add_(op, alpha=1.0 - decay)


def _nce(student, positive, temperature: float):
    """FedMKD Eq. (9): diagonal teacher positives, other student rows negatives."""
    # Teachers are detached upstream. Preserve the global-query attention path.
    s, t = F.normalize(student, dim=-1), F.normalize(positive, dim=-1)
    b = s.shape[0]
    pos = (s * t).sum(dim=-1, keepdim=True)
    neg = s @ s.T
    neg = neg.masked_fill(torch.eye(b, dtype=torch.bool, device=s.device), float("-inf"))
    logits = torch.cat((pos, neg), dim=1) / temperature
    labels = torch.zeros(b, dtype=torch.long, device=s.device)
    return F.cross_entropy(logits, labels)


class FedMKD:
    def __init__(self, models: list, config: dict, wire):
        if not models:
            raise ValueError("FedMKD requires at least one client model")
        self.models, self.config, self.wire = models, config, wire
        self.device = torch.device(config.get("device", "cpu"))
        self.gamma = float(config.get("gamma", 0.9))
        self.temperature = float(config.get("temperature", 0.2))
        self.ema_decay = float(config.get("ema_decay", 0.99))
        self.public_steps = int(config.get("public_steps", 2))
        self.alignment_steps = int(config.get("alignment_steps", 1))
        self.batch_size = int(config.get("local_batch", 64))
        self.public_batch = int(config.get("public_batch", 64))
        self.lr = float(config.get("lr", 0.001))
        # Global student is deliberately a new resource-tier model. Its features
        # and each client feature pass through their own 32-d projector so that
        # width-heterogeneous models can participate in the shared latent space.
        width = int(config.get("global_width", 256))
        self.global_model = common.SSLModel(width).to(self.device)
        self._global_target = (copy.deepcopy(self.global_model.encoder).to(self.device).eval(),
                               copy.deepcopy(self.global_model.projector).to(self.device).eval())
        self.models = [m.to(self.device) for m in models]
        self._targets = [
            (copy.deepcopy(m.encoder).to(self.device).eval(),
             copy.deepcopy(m.projector).to(self.device).eval()) for m in self.models
        ]

    @property
    def _step_size(self):
        return int(self.config.get("batch_size", self.batch_size))

    def _private_batches(self, x, seed):
        bsize = min(self.batch_size, len(x))
        for idx in common.batches(len(x), bsize, seed):
            yield x[idx].to(self.device)

    def round(self, private: list[torch.Tensor], public: torch.Tensor,
              seed: int, rnd: int) -> dict[str, Any]:
        if len(private) != len(self.models):
            raise ValueError("private data count must match client models")
        stats: dict[str, Any] = {"local_loss": [], "server_loss": [], "alignment_loss": []}
        # Client BYOL local SSL; only online model is trainable, target is EMA.
        for cid, (model, target, data) in enumerate(zip(self.models, self._targets, private)):
            model.train()
            opt = torch.optim.SGD(model.parameters(), lr=self.lr)
            losses = []
            for step, batch in enumerate(self._private_batches(data, seed + rnd * 1009 + cid)):
                opt.zero_grad(set_to_none=True)
                loss = _byol_loss(model, target[0], target[1], batch, seed + rnd * 7919 + step)
                loss.backward(); opt.step()
                _ema(target[0], model.encoder, self.ema_decay)
                _ema(target[1], model.projector, self.ema_decay)
                losses.append(float(loss.detach()))
            stats["local_loss"].append(sum(losses) / max(1, len(losses)))
            # Faithful payload direction: client online model to coordinator.
            model.load_state_dict(self.wire.state(model.state_dict(), cid, 0, f"fedmkd/client-{cid}/online"))

        # The coordinator computes client projected representations and trains
        # the global encoder/projector using adaptive attention distillation.
        pub = public.to(self.device)
        orders = common.batches(len(pub), self.public_batch, seed + rnd * 2003)
        server_opt = torch.optim.SGD(self.global_model.parameters(), lr=self.lr)
        server_losses = []
        for step in range(self.public_steps):
            batch = pub[orders[step % len(orders)]]
            if len(batch) < 2:
                break
            reps = []
            with torch.no_grad():
                for client in self.models:
                    reps.append(client.projector(client.encoder(batch)))
            teachers = F.normalize(torch.stack(reps, dim=1), dim=-1)  # B x N x k
            z_s = self.global_model.encoder(batch)
            r_s = F.normalize(self.global_model.projector(z_s), dim=-1)
            # Eq. 8: global query, client representations as key and value.
            with self.observer.phase('aggregation_seconds') if hasattr(self,'observer') else nullcontext():
                weights = torch.softmax(torch.einsum("bk,bnk->bn", r_s, teachers) /
                                        math.sqrt(teachers.shape[-1]), dim=1)
                positive = torch.einsum("bn,bnk->bk", weights, teachers)
            dloss = _nce(r_s, positive, self.temperature)
            # Retain global BYOL self-supervision, as in Eq. (10).
            self_loss = _byol_loss(self.global_model, self._global_target[0],
                                   self._global_target[1], batch,
                                   seed + rnd * 10007 + step * 2)
            loss = self_loss + self.gamma * dloss
            server_opt.zero_grad(set_to_none=True); loss.backward(); server_opt.step()
            _ema(self._global_target[0], self.global_model.encoder, self.ema_decay)
            _ema(self._global_target[1], self.global_model.projector, self.ema_decay)
            server_losses.append(float(loss.detach()))
        stats["server_loss"] = sum(server_losses) / max(1, len(server_losses))

        # Server-side global anchored alignment. Train one local online twin at
        # a time with global outputs as stopped target; retain client BYOL target.
        align_losses = []
        for cid, model in enumerate(self.models):
            opt = torch.optim.SGD(model.parameters(), lr=self.lr)
            for step in range(self.alignment_steps):
                batch = pub[orders[step % len(orders)]]
                if len(batch) < 2:
                    break
                # Follow official main.client_align -> client.align_train ->
                # BYOLModel.forward, which differs from printed Eq.12.
                # Global online encoder/projector is a fixed cross-view target.
                loss = _byol_loss(model,self.global_model.encoder,
                                  self.global_model.projector,batch,
                                  seed + rnd * 13007 + cid * 101 + step * 2)
                opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
                align_losses.append(float(loss.detach()))
            # only aligned online client model is returned to that client
            model.load_state_dict(self.wire.state(model.state_dict(), 0, cid, f"fedmkd/aligned-client-{cid}"))
        stats["alignment_loss"] = sum(align_losses) / max(1, len(align_losses))
        return stats

    @torch.no_grad()
    def representations(self, x: torch.Tensor) -> list[torch.Tensor]:
        x = x.to(self.device)
        return [m.encode(x).detach().cpu() for m in self.models]
