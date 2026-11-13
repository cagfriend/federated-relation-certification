import copy
from pathlib import Path

import pytest
from threadpoolctl import threadpool_limits

from experiments.private_prior import engine as prior_engine
from experiments.private_prior.fixture import prepare
from experiments.private_prior_compute import engine
from experiments.private_prior_compute.design import spec, schedule
from experiments.private_prior_compute.run import verify
from experiments.stl10_transfer.run import digest, seal, write_new


def test_matrix_and_orders():
    main, memory = schedule(), schedule(True)
    assert len(main)==12 and len(memory)==6
    assert len({(c['seed'],c['partition'],c['method']) for c in main})==12
    assert all(c['seed']==1002 for c in memory)
    assert spec('full').config.rounds==200


def test_methods_oracles_memory_replay_and_tamper(tmp_path):
    cfg = spec('smoke')
    directory = prepare(tmp_path/'cache',tmp_path/'source',cfg,1001,'iid')
    case = dict(seed=1001,partition='iid',case_id='strong_iid_seed1001')
    with threadpool_limits(limits=1):
        anchor = prior_engine.run(directory,cfg,branch='local_lr',fixture=True,progress=False)
        write_new(tmp_path/'anchor.json',seal(anchor))
        entry = dict(path=str(directory.resolve()), reference=str(tmp_path/'anchor.json'),
                     reference_sha256=digest(tmp_path/'anchor.json'))
        records = {}
        for name in ('B','E','D'):
            r = engine.run(directory,cfg,branch='local_lr',method=name,fixture=True,progress=False)
            r.update(memory_mode=False,process_peak_bytes=1)
            r = seal(r)
            verify(r,dict(case,method=name,memory=False),entry,'smoke')
            records[name] = r
            replay = engine.run(directory,cfg,branch='local_lr',method=name,fixture=True,progress=False,
                                enable_probes=False,validate=False,metrics=False)
            replay.update(memory_mode=True,process_peak_bytes=1)
            verify(seal(replay),dict(case,method=name,memory=True),entry,'smoke')
            missing_peak = copy.deepcopy(replay)
            missing_peak['process_peak_bytes'] = None
            with pytest.raises(ValueError,match='peak measurement'):
                verify(seal(missing_peak),dict(case,method=name,memory=True),entry,'smoke')
        bad = copy.deepcopy(records['D'])
        bad['round_records'][0]['teacher_relation_hashes'][0] = '0'*64
        with pytest.raises(ValueError,match='hard relation'):
            verify(seal(bad),dict(case,method='D',memory=False),entry,'smoke')
