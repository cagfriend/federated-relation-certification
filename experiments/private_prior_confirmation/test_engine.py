import copy

import pytest
from threadpoolctl import threadpool_limits

from experiments.private_prior_confirmation import engine, fixture
from experiments.private_prior_confirmation.design import spec, schedule, filename
from experiments.private_prior_confirmation.run import TRAJECTORY, verify
from experiments.private_prior_confirmation.support import write,seal,digest
from experiments.private_prior_compute import engine as previous


def test_frozen_spec_and_balanced_schedule():
    from pathlib import Path
    from experiments.private_prior_confirmation.support import read
    root=Path(__file__).resolve().parents[2]
    old=read(root/'experiments/private_prior_compute/results_full/environment.json')
    assert spec('full').json()==old['spec']
    runs=schedule('full')
    assert len(runs)==54 and len({filename(c) for c in runs})==54
    for cid in {c['case_id'] for c in runs}:
        group=[c for c in runs if c['case_id']==cid]
        for method in 'BED':
            assert sum(c['method']==method for c in group)==3
            assert sum(c['method']==method and c['position']==0 for c in group)==1


def test_fast_path_matches_oracle_and_previous_engine_and_rejects_tamper(tmp_path):
    s=spec('smoke','cpu')
    p=fixture.prepare(tmp_path/'cache',tmp_path/'source',s,1201,'iid')
    env=dict(preset='smoke',prepare_device='cpu',inputs={
        'strong_iid_seed1201':dict(path=str(p.resolve()),metadata_sha256=digest(p/'prepared.json'))})
    with threadpool_limits(limits=1):
        old=previous.run(p,s,branch='local_lr',fixture=True,progress=False,enable_probes=False,validate=False)
        for name in 'BED':
            audited=engine.run(p,s,branch='local_lr',method=name,fixture=True,progress=False,validate=True)
            fast=engine.run(p,s,branch='local_lr',method=name,fixture=True,progress=False,validate=False)
            assert audited['validation']['mismatches']==0
            assert audited['summary'][name]['final_head_digest']==old['summary']['B']['final_head_digest']
            for a,b in zip(audited['round_records'],fast['round_records']):
                assert all(a[k]==b[k] for k in TRAJECTORY)
            fast['repeat']=0;fast=seal(fast)
            case=next(c for c in schedule('smoke') if c['method']==name and c['repeat']==0)
            verify(fast,case,env,tmp_path)
            write(tmp_path/'runs'/filename(case),fast)
        changed=copy.deepcopy(fast)
        changed['round_records'][0]['target_digests'][0]='0'*64
        with pytest.raises(ValueError,match='trajectory'):
            verify(seal(changed),case,env,tmp_path)
