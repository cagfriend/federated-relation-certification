import csv
import json
import statistics as st
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.private_prior_confirmation.run import check_environment,verify
from experiments.private_prior_confirmation.design import cases,spec,filename
from experiments.private_prior_confirmation.support import read,digest
from experiments.private_prior_confirmation.report import report
from experiments.quantity_heterogeneity import data


def main():
    out=Path(__file__).resolve().parent
    source=ROOT/'experiments/private_prior_confirmation/results_full'
    env=read(source/'environment.json');check_environment(env)
    assert env['preset']=='full' and len(env['schedule'])==54
    completed=read(source/'completed.json');assert completed['runs']==54
    for n,h in completed['files'].items():assert digest(source/n)==h,n
    assert read(source/'finished.json')['completed_manifest_sha256']==digest(source/'completed.json')
    assert {p.name for p in (source/'runs').glob('*.json')}=={filename(c) for c in env['schedule']}
    for case in cases('full'):
        entry=env['inputs'][case['case_id']]
        assert digest(Path(entry['path'])/'prepared.json')==entry['metadata_sha256']
        data.verify(Path(entry['path']),spec('full',env['prepare_device']).config,case['seed'],case['partition'],profile='strong',fixture=False)
    records=[];timing=[]
    for case in env['schedule']:
        r=read(source/'runs'/filename(case));verify(r,case,env,source);records.append((case,r))
        vals=[x['pipeline_seconds'] for x in r['round_records']]
        timing.append(dict(case_id=case['case_id'],method=case['method'],repeat=case['repeat'],
                           median=st.median(vals),maximum=max(vals),max_round=vals.index(max(vals))+1,
                           over5median=sum(v>5*st.median(vals) for v in vals)))
    with tempfile.TemporaryDirectory(dir=out) as tmp:
        report(tmp,records,smoke=False)
        for name in ['decision.json','report.md','raw_runs.csv','seed_pairs.csv','quality.csv']:
            assert (Path(tmp)/name).read_bytes()==(source/name).read_bytes(),name
    qs=[]
    for case in cases('full'):
        r=next(r for c,r in records if c['case_id']==case['case_id'] and c['method']=='B' and c['repeat']==0)
        clients=r['metrics'][-1]['clients']
        late=[st.mean(row['teacher_positive_fractions'][c] for row in r['round_records'][160:]) for c in [0,3]]
        qs.append(dict(**case,late_small=late,final_test_max=[c['largest_cluster_fraction'] for c in clients],
                       final_acc=r['metrics'][-1]['mean']['acc'],
                       early_test_events=[dict(round=m['round'],client=c['client'],maximum=c['largest_cluster_fraction'])
                                          for m in r['metrics'] for c in m['clients']
                                          if c['occupied_clusters']==1 or c['largest_cluster_fraction']>=.99]))
    result=dict(integrity='passed',runs=54,round_records=10800,files_verified=len(completed['files']),
                frozen_sources=len(env['sources']),caches_verified=6,oracle_enabled=False,
                derived_reports_reproduced=5,quality=qs,timing=timing,exclusions=[],decision=read(source/'decision.json'))
    (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ['decision','timing']},indent=2))


if __name__=='__main__':main()
