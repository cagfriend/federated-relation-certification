"""Read-only verification of formal private-prior compute runs and reports."""
import csv
import json
import statistics as stats
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.private_prior_compute.run import read, check_environment, verify
from experiments.private_prior_compute.design import CASES, spec
from experiments.quantity_heterogeneity import data
from experiments.stl10_transfer.run import digest


def main():
    out = Path(__file__).resolve().parent
    results = ROOT/'experiments/private_prior_compute/results_full'
    env = read(results/'environment.json')
    assert env['preset']=='full' and env['memory_audit']
    check_environment(env)
    completed = read(results/'completed.json')
    assert (completed['runs'],completed['memory_runs']) == (12,6)
    assert read(results/'finished.json')['completed_manifest_sha256'] == digest(results/'completed.json')
    for name,expected in completed['files'].items():
        assert digest(results/name) == expected, name
    for case in CASES:
        entry = env['inputs'][case['case_id']]
        assert digest(Path(entry['path'])/'prepared.json')==entry['metadata_sha256']
        data.verify(Path(entry['path']),spec('full').config,case['seed'],case['partition'],profile='strong',fixture=False)
    records = {}
    relation_checks = candidate_checks = 0
    timing_diagnostics = []
    for memory, items in ((False,env['schedule']),(True,env['memory_schedule'])):
        folder = results/('memory' if memory else 'runs')
        assert {p.name for p in folder.glob('*.json')} == {c['case_id']+'_'+c['method']+'.json' for c in items}
        for case in items:
            r = read(folder/(case['case_id']+'_'+case['method']+'.json'))
            verify(r,case,env['inputs'][case['case_id']],'full')
            records[(case['case_id'],case['method'],memory)] = r
            if not memory:
                relation_checks += r['validation']['relation_comparisons']
                candidate_checks += r['validation']['candidate_membership_comparisons']
                values = [row['pipeline_seconds'] for row in r['round_records']]
                timing_diagnostics.append(dict(case_id=case['case_id'],method=case['method'],
                    median_round_seconds=stats.median(values),max_round_seconds=max(values),
                    max_round_index=values.index(max(values))+1,
                    rounds_over_5x_median=sum(v>5*stats.median(values) for v in values)))
    computed = []
    table = list(csv.DictReader((results/'comparisons.csv').open(encoding='utf-8-sig')))
    for case in CASES:
        cid = case['case_id']
        ss = {name: records[(cid,name,False)]['summary'][name] for name in ('B','E','D')}
        row = dict(**case, D_B_generation=1-ss['D']['generation_seconds']/ss['B']['generation_seconds'],
                   D_E_generation=1-ss['D']['generation_seconds']/ss['E']['generation_seconds'],
                   D_B_head=1-ss['D']['head_pipeline_seconds']/ss['B']['head_pipeline_seconds'],
                   D_E_head=1-ss['D']['head_pipeline_seconds']/ss['E']['head_pipeline_seconds'],
                   D_B_stage=1-ss['D']['measured_stage_seconds']/ss['B']['measured_stage_seconds'],
                   D_E_stage=1-ss['D']['measured_stage_seconds']/ss['E']['measured_stage_seconds'],
                   head_seconds={n:ss[n]['head_pipeline_seconds'] for n in ss},
                   recompute={n:ss[n]['teacher_recompute_fraction'] for n in ss},
                   persistent_bytes={n:ss[n]['persistent_method_array_bytes'] for n in ss})
        assert ss['B']['traffic']==ss['E']['traffic']==ss['D']['traffic']
        assert ss['B']['initial_traffic']==ss['E']['initial_traffic']==ss['D']['initial_traffic']
        reported = next(x for x in table if x['case_id']==cid and x['method']=='D')
        for key,label in [('D_B_head','head_saving_vs_B'),('D_E_head','head_saving_vs_E'),
                          ('D_B_generation','generation_saving_vs_B'),('D_E_generation','generation_saving_vs_E')]:
            assert abs(row[key]-float(reported[label]))<1e-12
        for key in ('acc','nmi','ari'):
            assert len({ss[n]['final_metrics']['mean'][key] for n in ss})==1
        tests = ss['D']['final_metrics']['clients']
        row['final_max_cluster_range']=[min(t['largest_cluster_fraction'] for t in tests),max(t['largest_cluster_fraction'] for t in tests)]
        row['final_single_cluster_clients']=sum(t['occupied_clusters']==1 for t in tests)
        if case['seed']==1002:
            peaks = {n: records[(cid,n,True)]['process_peak_bytes'] for n in ss}
            for n in ss:
                main = records[(cid,n,False)]
                replay = records[(cid,n,True)]
                assert [r['head_digest_after_public'] for r in main['round_records']]==[r['head_digest_after_public'] for r in replay['round_records']]
                assert [r['teacher_relation_hashes'] for r in main['round_records']]==[r['teacher_relation_hashes'] for r in replay['round_records']]
            row.update(memory_peak_bytes=peaks,D_B_peak_increase=peaks['D']/peaks['B']-1,
                       D_E_peak_increase=peaks['D']/peaks['E']-1)
        computed.append(row)
    result = dict(integrity='passed',main_runs=12,memory_runs=6,relation_comparisons=relation_checks,
                  candidate_membership_comparisons=candidate_checks,mismatches=0,
                  exclusions=[],cases=computed,timing_diagnostics=timing_diagnostics)
    (out/'audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
