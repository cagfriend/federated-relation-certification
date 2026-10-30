"""Read-only formal audit: hashes, partitions, trajectories, summaries, memory."""
import json,sys,tempfile,statistics as st
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from experiments.public_scaling.data import sha,idx,source_hashes
from experiments.public_scaling.config import from_json
from experiments.public_scaling.util import load_json,validate_payload
from experiments.noniid_clustering.data import partition_indices,verify,ensure_data
from experiments.noniid_clustering.run import check_case,check_environment
from experiments.noniid_clustering.report import reports
HERE=Path(__file__).parent;OUT=ROOT/'experiments/noniid_clustering/results_full'
def main():
    env=load_json(OUT/'environment.json');done=load_json(OUT/'completed.json');check_environment(env)
    for name,h in done['files'].items():assert sha(OUT/name)==h,name
    assert done['case_count']==9 and done['training_trajectories']==36 and done['memory_replays']==36
    cfg=from_json(env['config']);ensure_data(env['data_dir']);labels=idx(Path(env['data_dir'])/'train-labels-idx1-ubyte.gz')
    cases=[];profiles=[];splits=[]
    for seed in env['seeds']:
        order=list(env['partitions']);shift=seed%3;order=order[shift:]+order[:shift];public_ref=None
        for part in order:
            marker=load_json(OUT/f'prepared_{part}_seed_{seed}.json');directory=Path(marker['path'])
            assert sha(directory/'prepared.json')==marker['metadata_sha256'];verify(directory,cfg,seed,part)
            pub,priv,diag=partition_indices(labels,cfg.public_pool,len(cfg.dimensions),seed,part)
            np.testing.assert_array_equal(np.load(directory/'public_ids.npy'),pub)
            for i,ids in enumerate(priv):np.testing.assert_array_equal(np.load(directory/f'client_{i}_private_ids.npy'),ids)
            assert diag==load_json(directory/'partition.json')['diagnostics']
            if public_ref is None:public_ref=pub
            else:np.testing.assert_array_equal(public_ref,pub)
            c=load_json(OUT/f'{part}_seed_{seed}.json');check_case(c,cfg,seed,part,env,directory);cases.append(c)
            s=c['summary'];rr=c['round_records']
            for name in s:
                rows=[r for r in rr if r['method']==name]
                for phase in ('private','generation','exchange','public'):assert abs(s[name][phase+'_seconds']-sum(r[phase+'_seconds'] for r in rows))<1e-8
                assert abs(s[name]['shared_preparation_plus_head_seconds']-(c['common_preparation_seconds']+c['shared_loading_seconds']+s[name]['head_pipeline_seconds']))<1e-8
                if name!='Local':assert s[name]['traffic']==s['B']['traffic']
                p=load_json(OUT/f'memory_{part}_seed_{seed}_{name}.json');validate_payload(p)
                assert (p['identity'],p['seed'],p['partition'],p['method'])==(env,seed,part,name)
                assert p['final_head_digest']==s[name]['final_head_digest'] and p['persistent_array_bytes']==s[name]['persistent_method_array_bytes'] and p['process_peak_working_set_bytes']>0
            for name in ('Local','B','E','D'):
                p=load_json(OUT/f'memory_{part}_seed_{seed}_{name}.json');profiles.append({k:v for k,v in p.items() if k not in ('identity','payload_sha256')})
            splits.append(dict(seed=seed,partition=part,mean_entropy_nats=float(np.mean(diag['client_entropy_nats'])),missing_classes_per_client=list(map(len,diag['client_missing_classes'])),client_counts=diag['client_counts']))
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        reports(Path(tmp),cases,profiles)
        for name in ('report.md','summary.json','summary.csv','final_clients.csv','memory_summary.csv'):assert (Path(tmp)/name).read_bytes()==(OUT/name).read_bytes(),name
    summary=load_json(OUT/'summary.json');details=[]
    for part in env['partitions']:
        cc=[c for c in cases if c['partition']==part];d=dict(partition=part)
        d['ratios']=[r for r in summary['paired'] if r['partition']==part]
        d['quality_gains']=[r for r in summary['quality_gains'] if r['partition']==part]
        d['seed_quality']=[dict(seed=c['seed'],**{m:c['summary'][m]['final_metrics']['mean'] for m in ('Local','B')}) for c in cc]
        for m in ('Local','B'):
            allclients=[q for c in cc for ev in c['metrics'] if ev['method']==m for q in ev['clients']]
            d[m+'_min_occupied_clusters_all_evals']=min(q['occupied_clusters'] for q in allclients)
            d[m+'_max_largest_cluster_fraction_all_evals']=max(q['largest_cluster_fraction'] for q in allclients)
        d['memory_D_over_B_peak_median']=st.median(next(p['process_peak_working_set_bytes'] for p in profiles if (p['partition'],p['seed'],p['method'])==(part,c['seed'],'D'))/next(p['process_peak_working_set_bytes'] for p in profiles if (p['partition'],p['seed'],p['method'])==(part,c['seed'],'B')) for c in cc)
        d['persistent_D_minus_B_bytes']=cc[0]['summary']['D']['persistent_method_array_bytes']-cc[0]['summary']['B']['persistent_method_array_bytes']
        details.append(d)
    old=load_json(ROOT/'experiments/aggregator_recovery/results_full/completed.json')
    for name,h in old['files'].items():assert sha(ROOT/'experiments/aggregator_recovery/results_full'/name)==h
    result=dict(cases=len(cases),training_trajectories=36,memory_replays=len(profiles),verified_output_files=len(done['files']),unchanged_recovery_files=len(old['files']),relation_comparisons=sum(c['validation']['relation_comparisons'] for c in cases),candidate_membership_comparisons=sum(c['validation']['candidate_membership_comparisons'] for c in cases),mismatches=0,regenerated_reports_byte_identical=True,official_partitions_reconstructed=9,source_hashes=env['source_hashes'],core_source_hashes=source_hashes(),splits=splits,details=details)
    (HERE/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({k:v for k,v in result.items() if k not in ('source_hashes','core_source_hashes')},indent=2))
if __name__=='__main__':main()
