"""Audit saved graph experiment; never rerun training or edit original results."""
import json
from pathlib import Path
import statistics as st
import numpy as np
from experiments.public_scaling.config import from_json
from experiments.public_scaling.data import sha, source_hashes, verify_prepared
from experiments.public_scaling.graphs import make_graph
from experiments.public_scaling.run import checked_case, check_shared_cases, checked_profile
from experiments.public_scaling.util import load_json
from experiments.graph_density.analyze import paired


def main():
    root=Path(__file__).resolve().parents[2]
    p=root/'experiments/graph_density/results_graph'
    env,done=load_json(p/'environment.json'),load_json(p/'completed.json')
    assert done['source_hashes']==env['source_hashes']==source_hashes()
    assert env['seeds']==[404,505,606] and (done['case_count'],done['method_runs'],done['memory_profiles'])==(9,27,9)
    for name,h in done['file_hashes'].items(): assert sha(p/name)==h,name
    cases=[]; assets=0
    for seed in env['seeds']:
        marker=load_json(p/f'prepared_{seed}.json'); directory=Path(marker['path'])
        assert sha(directory/'prepared.json')==marker['metadata_sha256']
        meta=load_json(directory/'prepared.json'); verify_prepared(directory,meta); assets+=len(meta['files'])
        ids=[np.load(directory/f'client_{i}_private_ids.npy') for i in range(6)]
        public=np.load(directory/'public_ids.npy')
        assert sum(map(len,ids))==43616 and len(public)==16384
        assert len(np.unique(np.concatenate([public]+ids)))==60000
        previous=set()
        for cfg in sorted(env['plan'],key=lambda c:c['degree']):
            config=from_json(cfg); assert config.samples==4096 and config.rounds==200
            c=checked_case(p/f'{config.case_id}_seed_{seed}.json',config,seed,directory)
            graph=make_graph(4096,config.degree,seed); current=set(map(tuple,graph))
            assert previous<=current; previous=current
            import hashlib
            assert hashlib.sha256(graph.tobytes()).hexdigest()==c['graph_sha256']
            if config.degree==1:
                assert sha(p/f'{config.case_id}_seed_{seed}.json')==sha(root/f'experiments/public_scaling/results_public/{config.case_id}_seed_{seed}.json')
            for rnd in range(1,201):
                rows=[r for r in c['round_records'] if r['round']==rnd]
                assert len(rows)==3 and len({r['head_digest_after_public'] for r in rows})==1
                assert all(r['traffic']==rows[0]['traffic'] for r in rows)
                for k in ('private_loss','public_loss','public_optimizer_steps','private_optimizer_steps'):
                    assert all(r[k]==rows[0][k] for r in rows)
            ms=[[{k:v for k,v in m.items() if k!='method'} for m in c['metrics'] if m['method']==n] for n in ('B','E','D')]
            assert ms[0]==ms[1]==ms[2] and [m['round'] for m in ms[0]]==list(range(20,201,20))
            for n,s in c['summary'].items():
                rows=[r for r in c['round_records'] if r['method']==n]
                assert s['public_optimizer_steps']==9600*config.degree and s['private_optimizer_steps']==68400
                assert abs(sum(r['pipeline_seconds'] for r in rows)+s['initialization_seconds']-s['training_pipeline_seconds'])<1e-7
                assert abs(sum(r['teacher_forward_endpoints'] for r in rows[1:])/(4096*6*199)-s['teacher_recompute_fraction_after_bootstrap'])<1e-12
            cases.append(c)
    check_shared_cases(cases)
    for f in p.glob('memory_m*.json'):
        m=load_json(f); c=next(c for c in cases if c['seed']==m['seed'] and c['case_id']==m['case_id'])
        checked_profile(m,from_json(c['config']),m['seed'],c['summary'][m['method']]['persistent_method_array_bytes'])
    groups={}
    for degree in (1,4,8):
        group=sorted([c for c in cases if c['config']['degree']==degree],key=lambda c:c['seed'])
        met=[cl for c in group for me in c['metrics'] if me['method']=='D' for cl in me['clients']]
        groups[str(degree)]={
            'paired':{ref:{field:paired(group,ref,field) for field in ('generation_seconds','training_pipeline_seconds')} for ref in ('B','E')},
            'recompute_percent':{n:[100*c['summary'][n]['teacher_recompute_fraction_after_bootstrap'] for c in group] for n in ('E','D')},
            'certified_edge_percent_D':[100*c['summary']['D']['certified_edge_fraction_after_bootstrap'] for c in group],
            'B_generation_share_percent':[100*c['summary']['B']['generation_seconds']/c['summary']['B']['training_pipeline_seconds'] for c in group],
            'mean_final_ACC':[c['summary']['D']['final_metrics']['mean']['acc'] for c in group],
            'minimum_occupied_clusters':min(cl['occupied_clusters'] for cl in met),
            'maximum_cluster_fraction':max(cl['largest_cluster_fraction'] for cl in met),
            'median_traffic_bytes':st.median(c['summary']['D']['traffic']['total_bytes'] for c in group),
            'extra_persistent_mib_D_over_B':(group[0]['summary']['D']['persistent_method_array_bytes']-group[0]['summary']['B']['persistent_method_array_bytes'])/2**20}
    result=dict(root_json_hashes=len(done['file_hashes']),source_hashes=len(done['source_hashes']),prepared_files=assets,
        matching_paired_rounds=1800,matching_evaluation_triplets=90,
        relation_checks=sum(c['validation']['relation_comparisons'] for c in cases),
        candidate_checks=sum(c['validation']['candidate_membership_comparisons'] for c in cases),mismatches=0,
        groups=groups,note='Saved oracle counts verified; training and full oracle not rerun. Degree1 reused, only degree8 has isolated memory replay.')
    (Path(__file__).parent/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__': main()
