"""Candidate-set certificates for a frozen feature map and a linear head.

Only *real evaluations* refresh a sample's reference.  Parameter movement is
accumulated over every supplied snapshot, not just the latest round.  Floating
point guards are conservative numerical safeguards, not an IEEE proof.
"""
from __future__ import annotations

import numpy as np


def hard_relations(labels: np.ndarray, edges: np.ndarray) -> np.ndarray:
    return (labels[edges[:, 0]] == labels[edges[:, 1]]).astype(np.uint8)


def make_matching(samples: int, seed: int) -> np.ndarray:
    if samples < 2 or samples % 2:
        raise ValueError("The degree-one benchmark requires an even sample count")
    pairs = np.random.default_rng(seed).permutation(samples).reshape(-1, 2)
    pairs.sort(axis=1)
    return pairs[np.lexsort((pairs[:, 1], pairs[:, 0]))].astype(np.uint32)


class RelationGenerator:
    """One independent cache per method/client; no student forward reuse.

    ``mode='full'`` evaluates every sample. ``mode='relation'`` first creates
    candidate sets, then certifies disjoint sets or equal singleton sets. Only
    uncertain endpoints of unresolved edges are evaluated, after deduplication.
    K <= 64 is an explicit limit of the uint64 candidate representation.
    """

    def __init__(self, features: np.ndarray, weights: np.ndarray,
                 bias: np.ndarray, edges: np.ndarray, mode: str,
                 *, exact_integer: bool = False):
        if mode not in ("full", "relation", "point"):
            raise ValueError("Unknown generation mode")
        self.features, self.edges, self.mode = features, edges, mode
        self.samples, self.dimension = features.shape
        self.classes = len(bias)
        if not 1 <= self.classes <= 64:
            raise ValueError("Candidate bitsets require 1 <= K <= 64")
        if weights.shape != (self.classes, self.dimension):
            raise ValueError("Head shape mismatch")
        if len(edges) and (edges.min() < 0 or edges.max() >= self.samples):
            raise ValueError("Graph endpoint out of bounds")
        self.exact_integer = exact_integer
        scores = features @ weights.T + bias
        if not np.isfinite(scores).all():
            raise ValueError("Non-finite head scores")
        labels = scores.argmax(axis=1)
        self.initial_relations = hard_relations(labels, edges)
        self.round = 0
        if mode == "full":
            return
        dtype = np.int64 if exact_integer else np.float64
        # Prefix sums contain per-update pairwise variation budgets. A sample
        # stores the row corresponding to its last *actually computed* winner.
        self.weight_prefix = np.zeros((self.classes, self.classes), dtype=dtype)
        self.bias_prefix = np.zeros_like(self.weight_prefix)
        self.weight_at = np.zeros((self.samples, self.classes), dtype=dtype)
        self.bias_at = np.zeros_like(self.weight_at)
        self.gaps = scores[np.arange(self.samples), labels, None] - scores
        self.winners = labels.copy()
        self.last_evaluated = np.zeros(self.samples, dtype=np.int64)
        self.radius = (np.abs(features).sum(axis=1) if exact_integer
                       else np.linalg.norm(features, axis=1))
        self.previous_weights = weights.copy()
        self.previous_bias = bias.copy()
        self.powers = np.left_shift(np.uint64(1),
                                    np.arange(self.classes, dtype=np.uint64))

    def _advance(self, weights: np.ndarray, bias: np.ndarray) -> None:
        # Delta extraction and previous-head copies are deliberately timed.
        delta_w = weights - self.previous_weights
        delta_b = bias - self.previous_bias
        pair_delta = delta_w[:, None, :] - delta_w[None, :, :]
        if self.exact_integer:
            movement = np.abs(pair_delta).max(axis=2)
        else:
            movement = np.linalg.norm(pair_delta, axis=2)
        self.weight_prefix += movement
        self.bias_prefix += np.abs(delta_b[:, None] - delta_b[None, :])
        self.previous_weights = weights.copy()
        self.previous_bias = bias.copy()

    def candidate_matrix(self) -> np.ndarray:
        movement = self.weight_prefix[self.winners] - self.weight_at
        bias = self.bias_prefix[self.winners] - self.bias_at
        bound = self.radius[:, None] * movement + bias
        if not self.exact_integer:
            # Same practical guard as the existing numerical prototype. This
            # also retains ties; uncertain/tied samples are really evaluated.
            bound += 1e-10 * (1 + np.abs(bound) + np.abs(self.gaps))
        candidates = self.gaps <= bound
        return candidates

    def candidate_sets(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        candidates = self.candidate_matrix()
        bits = (candidates.astype(np.uint64) * self.powers).sum(
            axis=1, dtype=np.uint64)
        if np.any(bits == 0):
            raise ArithmeticError("Empty candidate set; do not reuse stale labels")
        singleton = (bits & (bits - np.uint64(1))) == 0
        return candidates, bits, singleton

    def _refresh(self, ids: np.ndarray, weights: np.ndarray,
                 bias: np.ndarray) -> None:
        if not len(ids):
            return
        scores = self.features[ids] @ weights.T + bias
        if not np.isfinite(scores).all():
            raise ArithmeticError("Non-finite recomputed scores")
        winners = scores.argmax(axis=1)  # ties: smallest local cluster index
        self.winners[ids] = winners
        self.gaps[ids] = scores[np.arange(len(ids)), winners, None] - scores
        self.weight_at[ids] = self.weight_prefix[winners]
        self.bias_at[ids] = self.bias_prefix[winners]
        self.last_evaluated[ids] = self.round

    def generate(self, weights: np.ndarray, bias: np.ndarray
                 ) -> tuple[np.ndarray, dict]:
        self.round += 1
        if self.mode == "full":
            scores = self.features @ weights.T + bias
            labels = scores.argmax(axis=1)
            return hard_relations(labels, self.edges), {
                "forward_endpoints": self.samples,
                "certified_edges_before_refresh": 0,
                "unresolved_edges_before_refresh": len(self.edges),
                "candidate_entries": self.samples * self.classes,
            }
        self._advance(weights, bias)
        left, right = self.edges.T
        if self.mode == "point":
            # Point certificates know a label only when its set is singleton.
            # Do not charge it for relation bitsets or intersection checks.
            candidates = self.candidate_matrix()
            sizes = candidates.sum(axis=1)
            if np.any(sizes == 0):
                raise ArithmeticError("Empty candidate set")
            singleton = sizes == 1
            known_edges = singleton[left] & singleton[right]
            ids = np.flatnonzero(~singleton)
            self._refresh(ids, weights, bias)
            return hard_relations(self.winners, self.edges), {
                "forward_endpoints": len(ids),
                "certified_edges_before_refresh": int(known_edges.sum()),
                "unresolved_edges_before_refresh": int((~known_edges).sum()),
                "candidate_entries": int(sizes.sum()),
            }
        candidates, bits, singleton = self.candidate_sets()
        different = (bits[left] & bits[right]) == 0
        same = singleton[left] & singleton[right] & (bits[left] == bits[right])
        unresolved = ~(different | same)
        needed = np.zeros(self.samples, dtype=bool)
        needed[self.edges[unresolved].ravel()] = True
        ids = np.flatnonzero(needed & ~singleton)
        self._refresh(ids, weights, bias)
        bits[ids] = self.powers[self.winners[ids]]
        singleton[ids] = True
        different_after = (bits[left] & bits[right]) == 0
        same_after = (singleton[left] & singleton[right]
                      & (bits[left] == bits[right]))
        if not np.all(different_after | same_after):
            raise ArithmeticError("An unresolved edge escaped exact recomputation")
        return same_after.astype(np.uint8), {
            "forward_endpoints": len(ids),
            "certified_edges_before_refresh": int((~unresolved).sum()),
            "unresolved_edges_before_refresh": int(unresolved.sum()),
            "candidate_entries": int(candidates.sum()),
        }

    def persistent_arrays(self) -> dict[str, int]:
        """Exclude shared feature/graph inputs; include method-owned arrays."""
        return {name: value.nbytes for name, value in vars(self).items()
                if isinstance(value, np.ndarray)
                and name not in ("features", "edges")}
