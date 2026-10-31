"""Read-only complete mechanism audit and seed-level descriptive diagnostics."""
import csv,json,sys,tempfile,statistics as st
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.public_scaling.data import sha,idx,source_hashes
from experiments.public_scaling.config import from_json
from experiments.public_scaling.util import load_json
from experiments.public_scaling.certification import hard_relations
from experiments.public_scaling.graphs import make_graph
from experiments.noniid_clustering.data import verify,ensure_data
from experiments.collaboration_mechanism.run import environment_check,check_case
from experiments.collaboration_mechanism.report import reports
HERE=Path(__file__).parent;OUT=ROOT/'experiments/collaboration_mechanism/results_full'
METHODS=('Local','Self','Aggregate','Shuffled')
def csvwrite(name,rows):
    with (HERE/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def med(v):return st.median(list(v))
def main():
    env=load_json(OUT/'environment.json');done=load_json(OUT/'completed.json');environment_check(env);cfg=from_json(env['config'])
    assert done['case_count']==9 and done['training_trajectories']==36 and done['mismatches']==0
    assert set(done['files'])=={p.name for p in OUT.iterdir() if p.is_file() and p.name!='completed.json' and not p.name.endswith('.part')}
    for name,h in done['files'].items():assert sha(OUT/name)==h,name
    ensure_data(env['data_dir']);labels=idx(Path(env['data_dir'])/'train-labels-idx1-ubyte.gz')
    cases=[];publics={};qualities=[];clients=[];grads=[];targets=[];occupancy=[]
    for seed in env['seeds']:
        order=list(env['partitions']);shift=seed%3;order=order[shift:]+order[:shift]
        for part in order:
            marker=load_json(OUT/f'prepared_{part}_seed_{seed}.json');directory=Path(marker['path'])
            assert sha(directory/'prepared.json')==marker['metadata_sha256'];verify(directory,cfg,seed,part)
            pub=np.load(directory/'public_ids.npy')[:cfg.samples]
            if seed in publics:np.testing.assert_array_equal(publics[seed],pub)
            publics[seed]=pub
            truth=hard_relations(labels[pub],make_graph(cfg.samples,cfg.degree,seed))
            refmeta=env['references'][f'{part}_{seed}'];assert sha(Path(refmeta['path']))==refmeta['sha256'];ref=load_json(refmeta['path'])
            c=load_json(OUT/f'{part}_seed_{seed}.json');check_case(c,cfg,seed,part,env,directory,truth,ref);cases.append(c)
            final={m:c['summary'][m]['final_metrics'] for m in METHODS}
            for a,b in [('Aggregate','Self'),('Aggregate','Shuffled'),('Aggregate','Local'),('Self','Local'),('Shuffled','Local')]:
                row=dict(partition=part,seed=seed,comparison=a+'-'+b)
                for key in ('acc','nmi','ari'):row[key+'_difference']=final[a]['mean'][key]-final[b]['mean'][key]
                row['worst_acc_difference']=min(q['acc'] for q in final[a]['clients'])-min(q['acc'] for q in final[b]['clients'])
                deltas=[x['acc']-y['acc'] for x,y in zip(final[a]['clients'],final[b]['clients'])]
                row['benefited_clients']=sum(v>0 for v in deltas);row['harmed_clients']=sum(v<0 for v in deltas)
                row['benefited_at_least_half_pp_clients']=sum(v>=0.005 for v in deltas);row['clients']=len(deltas)
                qualities.append(row)
                for x,y in zip(final[a]['clients'],final[b]['clients']):
                    clients.append(dict(partition=part,seed=seed,comparison=a+'-'+b,client=x['client'],width=x['width'],**{k+'_difference':x[k]-y[k] for k in ('acc','nmi','ari')}))
            for m in METHODS:
                allobs=[q for ev in c['metrics'] if ev['method']==m for q in ev['clients']]
                occupancy.append(dict(partition=part,seed=seed,method=m,final_mean_acc=final[m]['mean']['acc'],final_mean_nmi=final[m]['mean']['nmi'],final_mean_ari=final[m]['mean']['ari'],
                    min_occupied_all_checkpoints=min(q['occupied_clusters'] for q in allobs),max_cluster_fraction_all_checkpoints=max(q['largest_cluster_fraction'] for q in allobs),
                    min_occupied_final=min(q['occupied_clusters'] for q in final[m]['clients']),max_cluster_fraction_final=max(q['largest_cluster_fraction'] for q in final[m]['clients'])))
            for period in ('all_checkpoints','final'):
                dd=c['diagnostics'] if period=='all_checkpoints' else [r for r in c['diagnostics'] if r['round']==cfg.rounds]
                for anchor in METHODS:
                    for target in ('Self','Aggregate','Shuffled'):
                        rows=[r for r in dd if r['anchor']==anchor and r['target_kind']==target]
                        co=[r['gradient_cosine'] for r in rows if r['gradient_cosine'] is not None]
                        ratios=[r['weighted_public_private_norm_ratio'] for r in rows if r['weighted_public_private_norm_ratio'] is not None]
                        grads.append(dict(partition=part,seed=seed,period=period,anchor=anchor,target=target,observations=len(rows),
                            median_weighted_public_private_norm_ratio=med(ratios),median_cosine=med(co),negative_cosine_fraction=sum(v<0 for v in co)/len(co),
                            median_private_grad_norm=med(r['private_grad_norm'] for r in rows),median_public_grad_norm=med(r['public_grad_norm_raw'] for r in rows)))
            for period in ('all_rounds','final'):
                for m in ('Self','Aggregate','Shuffled'):
                    rows=[r for r in c['target_records'] if r['method']==m and (period=='all_rounds' or r['round']==cfg.rounds)]
                    keys=('target_mean','target_std','target_differs_from_self_fraction','mean_abs_target_minus_self','mean_other_clients_opposite_fraction','pairwise_client_relation_disagreement','shuffled_changed_edge_fraction','public_truth_brier','public_truth_positive_brier','public_truth_negative_brier','public_truth_constant_prior_brier','public_truth_target_gap')
                    targets.append(dict(partition=part,seed=seed,period=period,method=m,rounds=len(rows),**{k:med(r[k] for r in rows if r[k] is not None) for k in keys}))
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        reports(Path(tmp),cases)
        for name in ('summary.json','summary.csv','final_clients.csv','paired_quality.csv','diagnostics.csv','target_diagnostics.csv','report.md'):
            assert (Path(tmp)/name).read_bytes()==(OUT/name).read_bytes(),name
    old=ROOT/'experiments/noniid_clustering/results_full';previous=load_json(old/'completed.json')
    for name,h in previous['files'].items():assert sha(old/name)==h,name
    summary=[]
    for part in env['partitions']:
        for comp in sorted({r['comparison'] for r in qualities}):
            rows=[r for r in qualities if r['partition']==part and r['comparison']==comp]
            summary.append(dict(partition=part,comparison=comp,seeds=len(rows),
                **{k+'_median':med(r[k] for r in rows) for k in ('acc_difference','nmi_difference','ari_difference','worst_acc_difference')},
                acc_positive_seeds=sum(r['acc_difference']>0 for r in rows),acc_min=min(r['acc_difference'] for r in rows),acc_max=max(r['acc_difference'] for r in rows),
                benefited_clients=sum(r['benefited_clients'] for r in rows),harmed_clients=sum(r['harmed_clients'] for r in rows),benefited_at_least_half_pp_clients=sum(r['benefited_at_least_half_pp_clients'] for r in rows),total_client_pairs=sum(r['clients'] for r in rows)))
    for name,rows in [('seed_quality.csv',qualities),('client_quality.csv',clients),('gradient_summary.csv',grads),('target_summary.csv',targets),('cluster_summary.csv',occupancy)]:csvwrite(name,rows)
    primary=[q for q in summary if q['partition']=='dirichlet_0.1' and q['comparison'] in ('Aggregate-Self','Aggregate-Shuffled')]
    gate=all(q['seeds']==3 and q['acc_positive_seeds']==3 and q['acc_difference_median']>=0.005 for q in primary)
    result=dict(cases=len(cases),training_trajectories=36,output_files_verified=len(done['files']),source_hashes=env['source_hashes'],core_source_hashes=source_hashes(),preparation_source_hashes=env['preparation_source_hashes'],
        target_records_checked=sum(c['validation']['target_records_checked'] for c in cases),teacher_relation_entries=sum(c['validation']['teacher_relation_entries'] for c in cases),gradient_probe_rows=sum(len(c['diagnostics']) for c in cases),reference_round_method_pairs=sum(c['reference_validation']['round_method_pairs_checked'] for c in cases),
        mismatches=0,regenerated_reports_byte_identical=7,prepared_caches_verified=9,unchanged_previous_noniid_output_files=len(previous['files']),
        primary_exploratory_gate_passed=gate,quality_summary=summary,
        scope='Exact target-log reconstruction, source/output hashes, recorded historical Local/B replay and paired reporting. Teacher entries are processed relations, not independent high-precision forward proofs; diagnostic gradients are not causal mechanism proofs.')
    assert result['target_records_checked']==done['target_records_checked']==5400
    assert result['gradient_probe_rows']==done['gradient_probe_rows']==7128
    assert result['reference_round_method_pairs']==done['reference_round_method_pairs']==3600
    assert result['teacher_relation_entries']==done['teacher_relation_entries']==66355200
    (HERE/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if not k.endswith('source_hashes')},indent=2))
if __name__=='__main__':main()
