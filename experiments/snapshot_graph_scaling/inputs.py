"""Extend the E38 public bank without reselecting encoder snapshots."""

import hashlib
from pathlib import Path

import numpy as np
import torch

from experiments.external_pilot.prepare import selected_images
from experiments.private_corrected_guard.run import digest
from experiments.snapshot_certification_timing.design import require, seal, sealed, sha
from experiments.snapshot_certification_timing.inputs import load_verified, verify_preparation
from .design import SIZES, context_id

IMAGE_BYTES = 3*96*96


def raw_sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def pixels_sha(tensor):
    return hashlib.sha256(memoryview(tensor.numpy()).cast('B')).hexdigest()


def choose_bank(out, seed, train, count, binary, raw_digest):
    path = out/'banks'/f'{seed}.json'
    weights = path.with_suffix('.pt')
    old_ids = train['public_ids'].numpy()
    old_public = train['public']
    if binary is None:
        ids = np.arange(count, dtype=np.int64)
        extra = old_public[torch.arange(len(old_ids), count) % len(old_ids)].clone()
    else:
        size = binary.stat().st_size
        require(size % IMAGE_BYTES == 0 and size//IMAGE_BYTES >= count, 'Invalid STL-10 unlabeled data size')
        ids = np.random.default_rng(np.random.SeedSequence([seed,510])).permutation(size//IMAGE_BYTES)[:count]
    require(np.array_equal(ids[:len(old_ids)], old_ids) and len(np.unique(ids)) == count,
            'Expanded public bank does not preserve E38 sample IDs')
    declared = dict(seed=seed, count=count, raw_digest=raw_digest, ids=digest(ids), prefix=digest(old_public.numpy()))
    if path.with_suffix('.sha256.json').is_file():
        return verify_bank(path, declared)
    if binary is not None:
        # Use the original resize path in bounded chunks. Verify actual pixels as well as IDs.
        require(torch.equal(selected_images(binary, old_ids), old_public), 'E38 public images differ from dataset')
    path.parent.mkdir(parents=True, exist_ok=True)
    public = torch.empty((count, *old_public.shape[1:]), dtype=old_public.dtype)
    public[:len(old_ids)] = old_public
    if binary is None:
        public[len(old_ids):] = extra
    else:
        for begin in range(len(old_ids), count, 512):
            end = min(begin+512, count)
            public[begin:end] = selected_images(binary, ids[begin:end])
    temp = weights.with_suffix('.pt.part')
    torch.save(dict(public=public, ids=torch.from_numpy(ids)), temp)
    temp.replace(weights)
    sizes = SIZES['smoke' if binary is None else 'full']
    record = dict(**declared, payload_sha256=raw_sha(weights),
                  pixels={str(m): pixels_sha(public[:m]) for m in sizes})
    seal(path, record)
    return record


def verify_bank(path, declared=None):
    record = sealed(path)
    require(declared is None or all(record[k] == v for k, v in declared.items()), 'Bank configuration changed')
    require(raw_sha(path.with_suffix('.pt')) == record['payload_sha256'], 'Public bank payload changed')
    return record


def load_bank(out, case, train, metadata):
    payload = torch.load(out/'banks'/f'{case["seed"]}.pt', mmap=True, weights_only=True)
    size = case['public_size']
    require(len(payload['ids']) == metadata['count'] and digest(payload['ids'].numpy()) == metadata['ids']
            and len(payload['public']) == metadata['count'], 'Malformed public bank')
    old = train['public']
    require(torch.equal(payload['public'][:len(old)], old) and
            torch.equal(payload['ids'][:len(old)], train['public_ids']), 'Bank prefix differs from E38')
    require(pixels_sha(payload['public'][:size]) == metadata['pixels'][str(size)], 'Bank pixels changed in worker')
    return payload['public'][:size], payload['ids'][:size]


def selected_models(prep_dir, case, cfg, cache, history, anchors):
    part = case['partition']
    models, train, evaluation = load_verified(cache, part, cfg, history)
    path = prep_dir/f'{context_id(case)}.json'
    weights = path.with_suffix('.pt')
    prep = verify_preparation(path, weights, cache, cfg, history, anchors)
    for model, state in zip(models, torch.load(weights, weights_only=True), strict=True):
        model.load_state_dict(state)
    return models, train, evaluation, prep
