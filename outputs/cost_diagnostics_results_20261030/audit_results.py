"""Read-only audit and paired cost decomposition; no training or oracle replay."""
import json
from pathlib import Path
import statistics as st
import csv
from experiments.public_scaling.data import sha,source_hashes
from experiments.public_scaling.config import from_json
from experiments.public_scaling.run import verify_marker,checked_case
from experiments.public_scaling.util import load_json
from experiments.cost_diagnostics.run import own_sources,check_checkpoint
from experiments.cost_diagnostics.profiler import PHASES

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent


def main():
    p=ROOT/'experiments/cost_diagnostics/results_full'; identity=load_json(p/'environment.json');done=load_json(p/'completed.json')
    assert identity['source_hashes']==own_sources() and identity['core_source_hashes']==source_hashes()
    for n,h in done['files'].items():assert sha(p/n)==h,n
    reference=Path(identity['reference']);assert sha(reference/'completed.json')==identity['reference_completion_sha256']
    refenv=load_json(reference/'environment.json');refdone=load_json(reference/'completed.json')
    assert refenv['source_hashes']==identity['core_source_hashes']
    for n,h in refdone['file_hashes'].items():assert sha(reference/n)==h,n
    directories={s:verify_marker(load_json(reference/f'prepared_{s}.json')) for s in refenv['seeds']}
    assets=sum(len(load_json(d/'prepared.json')['files']) for d in directories.values())
    rows=[]; cases=[]
    for cfg in refenv['plan']:
        c=from_json(cfg)
        assert c.samples==4096 and c.rounds==200
        for s in refenv['seeds']:
            ref=checked_case(reference/f'{c.case_id}_seed_{s}.json',c,s,directories[s])
            case=load_json(p/f'{c.case_id}_seed_{s}.json');check_checkpoint(case,c,s,identity,ref);cases.append(case)
            pair={}
            for name in ('E','D'):
                rr=[r for r in case['records'] if r['method']==name and not r['bootstrap']]
                d=dict(degree=c.degree,seed=s,method=name,plain=sum(r['plain_wall_seconds'] for r in rr),
                       wall=sum(r['profiled_wall_seconds'] for r in rr),
                       other=sum(r['unassigned_seconds'] for r in rr),
                       selected=sum(r['statistics']['forward_endpoints'] for r in rr),
                       unresolved_union=None if name=='E' else sum(r['diagnostics']['unresolved_endpoint_union'] for r in rr),
                       candidate_size=sum(r['statistics']['candidate_entries'] for r in rr)/(len(rr)*c.samples),
                       **{ph:sum(r['phase_seconds'][ph] for r in rr) for ph in PHASES})
                for r in rr:
                    assert r['diagnostics']['selected_endpoints']==r['statistics']['forward_endpoints']
                    if name=='D':assert r['statistics']['forward_endpoints']<=r['diagnostics']['unresolved_endpoint_union']<=c.samples
                if name=='E':assert d['bitsets']==0
                pair[name]=d
            e,d=pair['E'],pair['D']
            rows.append(dict(degree=c.degree,seed=s,teacher_seconds_saved=e['teacher']-d['teacher'],
                extra_non_teacher_seconds=(d['wall']-d['teacher'])-(e['wall']-e['teacher']),
                profiled_seconds_saved=e['wall']-d['wall'],plain_seconds_saved=e['plain']-d['plain'],
                plain_D_over_E=d['plain']/e['plain'],profiled_D_over_E=d['wall']/e['wall'],
                phases_D_minus_E={ph:d[ph]-e[ph] for ph in PHASES},
                instrumented_over_plain={n:pair[n]['wall']/pair[n]['plain'] for n in ('E','D')},
                selected_E=e['selected'],selected_D=d['selected'],D_unresolved_union=d['unresolved_union'],
                recompute_E=e['selected']/(199*6*4096),recompute_D=d['selected']/(199*6*4096),
                candidate_size_E=e['candidate_size'],candidate_size_D=d['candidate_size']))
    assert len(cases)==done['case_count']==done['training_trajectories']==9 and done['mismatches']==0
    checks=sum(c['relation_comparisons'] for c in cases);assert checks==done['relation_comparisons']==383385600
    # Recompute the saved method-level summary from raw records.
    saved=load_json(p/'summary.json')
    with (p/'summary.csv').open(encoding='utf-8-sig',newline='') as f:csvrows=list(csv.DictReader(f))
    assert len(csvrows)==18
    for row in csvrows:
        case=next(c for c in cases if c['case_id']==row['case_id'] and c['seed']==int(row['seed']))
        rr=[r for r in case['records'] if r['method']==row['method'] and not r['bootstrap']]
        for ph in PHASES:assert abs(float(row[ph+'_seconds'])-sum(r['phase_seconds'][ph] for r in rr))<1e-10
    for cid in saved:
        for n in ('E','D'):
            for key,value in saved[cid][n].items():
                expected=st.median(float(r[key]) for r in csvrows if r['case_id']==cid and r['method']==n)
                assert abs(value-expected)<1e-8,(cid,n,key)
    groups={}
    for degree in (1,4,8):
        rr=[r for r in rows if r['degree']==degree]
        groups[str(degree)]={k:st.median(r[k] for r in rr) for k in ('teacher_seconds_saved','extra_non_teacher_seconds','profiled_seconds_saved','plain_seconds_saved','plain_D_over_E','profiled_D_over_E','recompute_E','recompute_D')}
        groups[str(degree)]['phase_D_minus_E']={ph:st.median(r['phases_D_minus_E'][ph] for r in rr) for ph in PHASES}
        groups[str(degree)]['instrumented_over_plain']={n:st.median(r['instrumented_over_plain'][n] for r in rr) for n in ('E','D')}
    result=dict(case_count=9,records=sum(len(c['records']) for c in cases),post_bootstrap_records=21492,
                validated_result_hashes=len(done['files']),validated_reference_hashes=len(refdone['file_hashes']),
                validated_prepared_files=assets,validated_diagnostic_sources=len(identity['source_hashes']),
                validated_core_sources=len(identity['core_source_hashes']),oracle_comparisons_recorded=checks,mismatches=0,
                groups=groups,raw_pairs=rows,
                limits=['No training or oracle rerun. Cache equality and E head/message equality were runtime assertions in hashed code; full caches and head hashes are not persisted in diagnostic case files.',
                        'Profiled phase wall-clock costs are diagnostic and include instrumentation/load effects; not an end-to-end speedup or policy validation.',
                        'Each column is a median of three within-seed differences; separately reported medians need not sum.'])
    (OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('raw_pairs','limits')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
