"""Read-only full public-budget audit; retain all timing records and flag delays."""
import csv,json,sys,tempfile,statistics as st
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.public_scaling.data import sha,source_hashes
from experiments.public_scaling.util import load_json
from experiments.noniid_clustering.data import verify
from experiments.public_budget.design import spec_from_json,PARTITIONS,SEEDS,METHODS
from experiments.public_budget.run import check_environment,check_case,check_profile
from experiments.public_budget.report import reports
HERE=Path(__file__).parent;OUT=ROOT/'experiments/public_budget/results_full'
PHASES=('private','generation','exchange','public','pipeline')
def med(v):return st.median(list(v))
def csvwrite(name,rows):
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
    env=load_json(OUT/'environment.json');done=load_json(OUT/'completed.json');check_environment(env)
    assert done['case_count']==18 and done['training_trajectories']==54 and done['memory_replays']==18
    assert set(done['files'])=={p.name for p in OUT.iterdir() if p.is_file() and p.name!='completed.json' and not p.name.endswith('.part')}
    for name,h in done['files'].items():assert sha(OUT/name)==h,name
    specs=[spec_from_json(v) for v in env['plan']];cases=[];profiles=[];delays=[];costs=[];coverage=[]
    for seed in SEEDS:
        for part in PARTITIONS:
            marker=load_json(OUT/f'prepared_{part}_seed_{seed}.json');directory=Path(marker['path'])
            assert sha(directory/'prepared.json')==marker['metadata_sha256'];verify(directory,specs[0].config,seed,part)
            order=list(specs);shift=seed%3;order=order[shift:]+order[:shift]
            for spec in order:
                c=load_json(OUT/f'{part}_{spec.case_id}_seed_{seed}.json')
                refmeta=env['references'].get(f'{part}_{seed}') if spec.case_id==specs[0].case_id else None
                ref=None
                if refmeta:
                    assert sha(Path(refmeta['path']))==refmeta['sha256'];ref=load_json(refmeta['path'])
                check_case(c,spec,part,seed,env,directory,ref);cases.append(c)
                coverage.append(dict(partition=part,seed=seed,case_id=spec.case_id,**c['coverage']))
                for base in ('B','E'):
                    a,b=c['summary']['D'],c['summary'][base]
                    costs.append(dict(partition=part,seed=seed,case_id=spec.case_id,comparison='D/'+base,
                        **{p+'_ratio':a[p]/b[p] for p in ('generation_seconds','head_pipeline_seconds','with_shared_preparation_seconds')},
                        **{p+'_saved_seconds':b[p]-a[p] for p in ('generation_seconds','head_pipeline_seconds','with_shared_preparation_seconds')},
                        D_generation_fraction=a['generation_fraction'],reference_generation_fraction=b['generation_fraction'],
                        D_teacher_recompute_fraction=a['teacher_recompute_fraction'],reference_teacher_recompute_fraction=b['teacher_recompute_fraction'],
                        extra_persistent_bytes=a['persistent_method_array_bytes']-b['persistent_method_array_bytes'],traffic_byte_difference=a['traffic']['total_bytes']-b['traffic']['total_bytes']))
                for m in METHODS:
                    rows=[r for r in c['round_records'] if r['method']==m]
                    for phase in PHASES:
                        key=phase+'_seconds';normal=med(r[key] for r in rows)
                        for row in rows:
                            if row[key]>max(1.,20*normal):
                                delays.append(dict(partition=part,seed=seed,case_id=spec.case_id,method=m,round=row['round'],phase=phase,seconds=row[key],method_case_phase_median=normal,multiple=row[key]/normal,
                                    private_seconds=row['private_seconds'],generation_seconds=row['generation_seconds'],exchange_seconds=row['exchange_seconds'],public_seconds=row['public_seconds'],pipeline_seconds=row['pipeline_seconds'],
                                    unassigned_pipeline_seconds=row['pipeline_seconds']-sum(row[p+'_seconds'] for p in ('private','generation','exchange','public'))))
                if spec.policy=='fixed':
                    for m in METHODS:
                        p=load_json(OUT/f'memory_{part}_{spec.case_id}_{m}_seed_{seed}.json');check_profile(p,c,env)
                        profiles.append({k:v for k,v in p.items() if k not in ('identity','payload_sha256')})
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        reports(Path(tmp),cases,profiles)
        for name in ('summary.json','summary.csv','paired_cost.csv','budget_effects.csv','quality_guardrails.csv','final_clients.csv','memory_summary.csv','report.md'):
            assert (Path(tmp)/name).read_bytes()==(OUT/name).read_bytes(),name
    assert done['relation_comparisons']==sum(c['validation']['relation_comparisons'] for c in cases)==398131200
    assert done['candidate_membership_comparisons']==sum(c['validation']['candidate_membership_comparisons'] for c in cases)==530841600
    assert done['historical_anchor_round_method_pairs']==sum(c['reference_validation'].get('round_method_pairs',0) for c in cases)==3600
    summary=[]
    for part in PARTITIONS:
        for spec in specs:
            for comp in ('D/B','D/E'):
                rows=[r for r in costs if r['partition']==part and r['case_id']==spec.case_id and r['comparison']==comp]
                summary.append(dict(partition=part,case_id=spec.case_id,comparison=comp,
                    **{k:med(r[k] for r in rows) for k in rows[0] if k not in ('partition','seed','case_id','comparison')},
                    head_wins=sum(r['head_pipeline_seconds_ratio']<1 for r in rows),head_ratio_min=min(r['head_pipeline_seconds_ratio'] for r in rows),head_ratio_max=max(r['head_pipeline_seconds_ratio'] for r in rows)))
    guards=list(csv.DictReader((OUT/'quality_guardrails.csv').read_text(encoding='utf-8').splitlines()))
    effects=list(csv.DictReader((OUT/'budget_effects.csv').read_text(encoding='utf-8').splitlines()))
    budget_summary=[];guard_summary=[];memory=[]
    for part in PARTITIONS:
        gg=[g for g in guards if g['partition']==part]
        guard_summary.append(dict(partition=part,paired_seeds=len(gg),within_guardrail=sum(g['within_acc_guardrail']=='True' for g in gg),acc_delta_median=med(float(g['acc_delta']) for g in gg),acc_delta_min=min(float(g['acc_delta']) for g in gg),acc_delta_max=max(float(g['acc_delta']) for g in gg),nmi_delta_median=med(float(g['nmi_delta']) for g in gg),ari_delta_median=med(float(g['ari_delta']) for g in gg),worst_acc_delta_median=med(float(g['worst_client_acc_delta']) for g in gg),min_same_client_acc_delta_min=min(float(g['min_same_client_acc_delta']) for g in gg)))
        for m in METHODS:
            ee=[e for e in effects if e['partition']==part and e['method']==m]
            budget_summary.append(dict(partition=part,method=m,head_fixed_over_full_median=med(float(e['head_pipeline_seconds_fixed_over_full']) for e in ee),head_seconds_saved_median=med(float(e['head_pipeline_seconds_saved_seconds_full_minus_fixed']) for e in ee),with_preparation_fixed_over_full_median=med(float(e['with_shared_preparation_seconds_fixed_over_full']) for e in ee),generation_fraction_change_median=med(float(e['generation_fraction_change_fixed_minus_full']) for e in ee)))
        for base in ('B','E'):
            pp=[p for p in profiles if p['partition']==part]
            ratios=[];diff=[]
            for seed in SEEDS:
                d=next(p for p in pp if p['seed']==seed and p['method']=='D');b=next(p for p in pp if p['seed']==seed and p['method']==base)
                ratios.append(d['process_peak_working_set_bytes']/b['process_peak_working_set_bytes']);diff.append(d['process_peak_working_set_bytes']-b['process_peak_working_set_bytes'])
            memory.append(dict(partition=part,comparison='D/'+base,peak_ratio_median=med(ratios),peak_difference_bytes_median=med(diff)))
    oldfiles=0
    for name in ('noniid_clustering','collaboration_mechanism'):
        output=ROOT/f'experiments/{name}/results_full';before=load_json(output/'completed.json')
        for path,h in before['files'].items():assert sha(output/path)==h,path
        oldfiles+=len(before['files'])
    csvwrite('paired_cost_audit.csv',costs);csvwrite('coverage_audit.csv',coverage)
    if delays:csvwrite('timing_delay_flags.csv',sorted(delays,key=lambda d:d['seconds'],reverse=True))
    result=dict(cases=18,training_trajectories=54,memory_replays=18,verified_output_files=len(done['files']),relation_comparisons=398131200,candidate_membership_comparisons=530841600,historical_anchor_round_method_pairs=3600,mismatches=0,
        regenerated_reports_byte_identical=8,prepared_groups_verified=6,unchanged_previous_result_files=oldfiles,
        source_hashes=env['source_hashes'],core_source_hashes=source_hashes(),preparation_source_hashes=env['preparation_source_hashes'],
        cost_summary=summary,quality_guardrails=guard_summary,budget_effects=budget_summary,memory_summary=memory,
        timing_delay_flags=sorted(delays,key=lambda d:d['seconds'],reverse=True),all_original_timings_retained=True,
        delay_flag_rule='Descriptive only: phase > max(1 second,20 times own method/case phase median); no records excluded or replaced',
        scope='Known-seed paired serial CPU timing; not isolated-process/new-seed timing confirmation. Large measured intervals cannot be causally assigned from these logs.')
    (HERE/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_hashes','core_source_hashes','preparation_source_hashes','timing_delay_flags')},indent=2))
    print('TOP FLAGGED INTERVALS:');print(json.dumps(result['timing_delay_flags'][:8],indent=2))
if __name__=='__main__':main()
