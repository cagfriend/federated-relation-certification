"""Small-pilot Hetero-SSFL adaptation: local SimSiam + representation CKA."""

from __future__ import annotations

from typing import Any

import torch

try:  # package and direct-file import modes
    from . import common
except ImportError:  # pragma: no cover - exercised by the pilot runner
    import common  # type: ignore


def _centered_gram(z: torch.Tensor) -> torch.Tensor:
    """Linear kernel on rows, centered over the shared RAD examples."""
    z = z - z.mean(dim=0, keepdim=True)
    gram = z @ z.T
    return gram - gram.mean(dim=0, keepdim=True) - gram.mean(dim=1, keepdim=True) + gram.mean()


def _kernel_similarity(ka: torch.Tensor, kb: torch.Tensor, eps: float = 1e-12) -> torch.Tensor:
    ka = ka - ka.mean(dim=0, keepdim=True) - ka.mean(dim=1, keepdim=True) + ka.mean()
    kb = kb - kb.mean(dim=0, keepdim=True) - kb.mean(dim=1, keepdim=True) + kb.mean()
    denom = torch.linalg.vector_norm(ka) * torch.linalg.vector_norm(kb)
    return (ka * kb).sum() / denom.clamp_min(eps)


class Hetero:
    """Hetero-SSFL style personalized encoders with kernel alignment on public RAD.

    Each model is trained locally; only public-data representations/kernels cross
    the simulated wire. No parameters are averaged or exchanged.
    """

    def __init__(self, models: list[torch.nn.Module], config: dict[str, Any], wire: Any):
        if not models:
            raise ValueError("Hetero requires at least one client model")
        self.models = models
        self.config = config
        self.wire = wire
        self._target_kernel: torch.Tensor | None = None

    def _public_reps(self, public: torch.Tensor, tag: str) -> list[torch.Tensor]:
        reps = []
        for client, model in enumerate(self.models):
            model.eval()
            with torch.no_grad():
                z = model.predictor(model(public))
            # The predictor output is Phi in the paper; detach before transmission.
            reps.append(self.wire.tensor(z.detach(), client, 0, f"{tag}:repr"))
        return reps

    def _aggregate_kernel(self, reps: list[torch.Tensor], tag: str) -> torch.Tensor:
        # Reps have already crossed client->server in _public_reps; kernel
        # construction and averaging happen at the server without another send.
        kernels = [_centered_gram(z) for z in reps]
        # Paper's client weights are configurable; this pilot uses uniform weights.
        return torch.stack(kernels, dim=0).mean(dim=0)

    def representations(self, x: torch.Tensor) -> list[torch.Tensor]:
        out = []
        for model in self.models:
            model.eval()
            with torch.no_grad():
                out.append(model.encode(x))
        return out

    def round(self, private: list[torch.Tensor], public: torch.Tensor, seed: int, rnd: int) -> dict[str, Any]:
        if len(private) != len(self.models):
            raise ValueError("private must contain one tensor per model")
        device = next(self.models[0].parameters()).device
        public = public.to(device=device, dtype=torch.float32)

        # Round t uses the previous round's peer target. The initial target is
        # formed from the initialized client models, matching Algorithm 1's Kbar.
        if self._target_kernel is None:
            initial_reps = self._public_reps(public, f"r{rnd}:initial")
            self._target_kernel = self._aggregate_kernel(initial_reps, f"r{rnd}:initial")
        target = self._target_kernel

        lr = float(self.config.get("lr", 1e-3))
        batch_size = int(self.config.get("local_batch", 64))
        public_batch = int(self.config.get("public_batch", 64))
        public_steps = int(self.config.get("public_steps", 2))
        mu = float(self.config.get("alignment_weight", 1.0))
        losses: list[float] = []
        steps = 0

        for client, (model, data) in enumerate(zip(self.models, private)):
            client_target = self.wire.tensor(target, 0, client, f"r{rnd}:target")
            data = data.to(device=device, dtype=torch.float32)
            model.train()
            optimizer = torch.optim.Adam(model.parameters(), lr=lr)
            # Exactly one shuffled local epoch, as specified for this pilot.
            for ids in common.batches(len(data), batch_size, seed + rnd * 1009 + client):
                x = data[ids].to(device)
                a = common.augment(x, seed + rnd * 1009 + client * 97 + steps * 2)
                b = common.augment(x, seed + rnd * 1009 + client * 97 + steps * 2 + 1)
                optimizer.zero_grad(set_to_none=True)
                ssl = common.simsiam_loss(model, a, b)
                align_terms = []
                # RAD batches share example identities across clients; public
                # views are deterministic and only the local prediction pathway
                # receives gradients from this client-specific CKA objective.
                for pstep in range(public_steps):
                    pids = common.batches(
                        len(public), public_batch,
                        seed + rnd * 4099 + pstep,
                    )
                    if not pids:
                        continue
                    px = public[pids[pstep % len(pids)]]
                    pz = model.predictor(model(px))
                    # Compare the matching RAD examples; different feature widths
                    # are handled by comparing their batch Gram matrices.
                    target_batch = client_target[pids[pstep % len(pids)]][:, pids[pstep % len(pids)]]
                    align_terms.append(1.0 - _kernel_similarity(_centered_gram(pz), target_batch))
                align = torch.stack(align_terms).mean() if align_terms else ssl.new_zeros(())
                loss = ssl + mu * align
                loss.backward()
                optimizer.step()
                losses.append(float(loss.detach().cpu()))
                steps += 1

        # Server aggregates public representations (not model weights) for next round.
        reps = self._public_reps(public, f"r{rnd}:final")
        self._target_kernel = self._aggregate_kernel(reps, f"r{rnd}:final")
        return {"losses": losses, "steps": steps}
