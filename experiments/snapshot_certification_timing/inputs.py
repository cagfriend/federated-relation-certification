"""Verify the original cache and measure common preparation once per case."""

from pathlib import Path
from time import perf_counter

import torch
from torch import nn
from torch.nn import functional as F

from experiments.external_pilot.common import SSLModel, model_digest
from experiments.external_pilot.prepare import load, prepare, read, sha
from experiments.snapshot_external_comparison.selection import schedule, select_models
from .design import case_id, require, seal, sealed, selection_core


def cache_location(cache, out, cfg, part, data_dir):
    for directory in (cache/str(cfg['seed']), out/'recreated_cache'/str(cfg['seed'])):
        if (directory/part/'manifest.json').is_file():
            return directory
    require(data_dir is not None, f'Missing E38 cache for {cfg["seed"]}/{part}; supply --cache or --data-dir')
    directory = out/'recreated_cache'/str(cfg['seed'])
    prepare(directory, data_dir, cfg)
    return directory


def load_verified(directory, part, cfg, old):
    models, train, meta = load(directory, part, cfg)
    require(meta['files'] == old['input_files'] and meta['initial_model_digest'] == old['initial_model_digest'],
            'Training/test payload or original cached encoder differs from E38')
    evaluation = torch.load(directory/part/'evaluation.pt', weights_only=True)
    return models, train, evaluation


def warm_encoders(cfg, train):
    # Same seed, batching and arithmetic as the E38 preparation, without image loading or checkpoint writes.
    # Equalize one-time library initialization before measuring each case.
    torch.manual_seed(cfg['seed'])
    scratch = nn.Linear(2, 2)
    bootstrap = torch.optim.Adam(scratch.parameters())
    scratch(torch.ones(1, 2)).sum().backward()
    bootstrap.step()
    start = perf_counter()
    models = []
    for c, width in enumerate(cfg['widths']):
        x = train['private'][c]
        torch.manual_seed(cfg['seed']+220+c)
        model = SSLModel(width)
        decoder = nn.Linear(width, x.shape[1])
        opt = torch.optim.Adam(list(model.encoder.parameters()) + list(decoder.parameters()), lr=cfg['ae_lr'])
        for ix in schedule(cfg, c, len(x)):
            batch = x[ix]
            opt.zero_grad()
            reconstruction = torch.sigmoid(decoder(F.relu(model.encoder.linear(batch))))
            F.mse_loss(reconstruction, batch).backward()
            opt.step()
        models.append(model)
    return models, perf_counter()-start


def preparation(out, case, cfg, directory, old, anchors):
    part = case['partition']
    path = out/'preparation'/f'{case_id(case)}.json'
    weights = path.with_suffix('.pt')
    if path.with_suffix('.sha256.json').exists():
        return verify_preparation(path, weights, directory, cfg, old, anchors)
    _, train, _ = load_verified(directory, part, cfg, old)
    terminal, ae_s = warm_encoders(cfg, train)
    require(model_digest(terminal) == old['initial_model_digest'], 'Same-machine AE replay differs from E38')
    start = perf_counter()
    models, records = select_models(cfg, terminal, train)
    selection_s = perf_counter()-start
    records = selection_core(records)
    # JSON archive keys for candidate steps are strings.
    for r in records:
        r['candidates'] = {str(k): v for k, v in r['candidates'].items()}
    require(records == selection_core(old['selection']) and model_digest(models) == old['selected_model_digest'],
            'Snapshot screening or selected encoder differs from E38')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = weights.with_suffix('.pt.part')
    torch.save([m.state_dict() for m in models], temp)
    temp.replace(weights)
    payload = dict(source_cache=str(directory), cfg=cfg, anchors=anchors, input_files=old['input_files'],
                   selected_model_digest=old['selected_model_digest'], selection=records, ae_seconds=ae_s,
                   selection_seconds=selection_s, selected_sha256=sha(weights))
    seal(path, payload)
    return payload


def verify_preparation(path, weights, directory, cfg, old, anchors):
    record = sealed(path)
    require(Path(record['source_cache']) == directory and record['cfg'] == cfg and record['anchors'] == anchors
            and record['input_files'] == old['input_files']
            and record['selected_sha256'] == sha(weights)
            and record['selected_model_digest'] == old['selected_model_digest']
            and record['selection'] == selection_core(old['selection']), 'Prepared state changed')
    return record
