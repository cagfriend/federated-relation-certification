"""Read-only audit of completed policy replays; independently recompute summaries."""
import csv
import json
from pathlib import Path
import statistics as st
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.public_scaling.data import sha, source_hashes
from experiments.public_scaling.util import load_json
from experiments.path_selection.run import sources, references, check_case, report

HERE=Path(__file__).resolve().parent


def main():
    output=ROOT/'experiments/path_selection/results_full'
    identity=load_json(output/'environment.json');done=load_json(output/'completed.json')
    assert identity['source_hashes']==sources()
    assert identity['core_source_hashes']==source_hashes()
    assert sha(Path(identity['reference'])/'completed.json')==identity['reference_completion_sha256']
    for name, checksum in done['files'].items():
        assert Path(name).name==name and sha(output/name)==checksum,name
    env,plan,directories,refs=references(Path(identity['reference']),'full')
    cases=[];width_rows=[];pairs=[];state_matches=[]
    for seed in env['seeds']:
        configs={c.case_id:c for c in plan}
        for cid in env['execution_order'][str(seed)]:
            cfg=configs[cid];assert cfg.samples==4096 and cfg.rounds==200
            case=load_json(output/f'{cid}_seed_{seed}.json')
            check_case(case,cfg,seed,identity,refs[(cid,seed)]);cases.append(case)
            records={(r['round'],r['client'],r['policy']):r for r in case['records']}
            static_base='D' if cfg.degree==1 else 'E'
            for candidate,baseline in (('static',static_base),('adaptive','E')):
                matches=sum(records[(r,c,candidate)]['cache_digest']==records[(r,c,baseline)]['cache_digest']
                            for r in range(1,cfg.rounds+1) for c in range(len(cfg.dimensions)))
                state_matches.append(dict(case_id=cid,seed=seed,policy=candidate,baseline=baseline,
                                          matching_cache_digests=matches,total=cfg.rounds*len(cfg.dimensions)))
                if candidate=='static' or cfg.degree==8:
                    assert matches==cfg.rounds*len(cfg.dimensions)
            for width in sorted(set(cfg.dimensions)):
                width_group={}
                for policy in ('E','D','static','adaptive'):
                    rr=[r for r in case['records'] if r['policy']==policy and r['width']==width]
                    post=[r for r in rr if not r['bootstrap']]
                    row=dict(case_id=cid,degree=cfg.degree,seed=seed,width=width,policy=policy,
                        generation_seconds=sum(r['generation_seconds'] for r in rr),
                        post_generation_seconds=sum(r['generation_seconds'] for r in post),
                        decision_seconds=sum(r['statistics']['decision_seconds'] for r in post),
                        D_calls=sum(r['statistics']['selected_path']=='D' for r in post),
                        E_calls=sum(r['statistics']['selected_path']=='E' for r in post),
                        switches=sum(r['statistics']['switched'] for r in post),
                        refresh_fraction=sum(r['statistics']['forward_endpoints'] for r in post)/(len(post)*cfg.samples))
                    width_rows.append(row);width_group[policy]=row
                for policy,baseline in (('D','E'),('adaptive','static')):
                    a,b=width_group[policy],width_group[baseline]
                    pairs.append(dict(case_id=cid,degree=cfg.degree,seed=seed,width=width,policy=policy,baseline=baseline,
                        generation_ratio=a['generation_seconds']/b['generation_seconds'],
                        extra_seconds=a['generation_seconds']-b['generation_seconds']))
    assert len(cases)==done['case_count']==done['shared_training_trajectories']==9
    assert done['policy_replays']==36 and done['mismatches']==0
    assert sum(c['relation_comparisons'] for c in cases)==done['relation_comparisons']==383385600
    assert sum(c['candidate_membership_comparisons'] for c in cases)==done['candidate_membership_comparisons']==176947200
    with tempfile.TemporaryDirectory(dir=HERE) as temporary:
        report(Path(temporary),cases)
        for name in ('summary.json','summary.csv','report.md'):
            assert (Path(temporary)/name).read_bytes()==(output/name).read_bytes(),name
    saved=load_json(output/'summary.json')
    # Independent seed-pair arithmetic, without the experiment's report function.
    independent=[]
    for degree in (1,4,8):
        for policy,baseline in (('D','E'),('static','E'),('adaptive','static')):
            for metric in ('generation_with_bootstrap_seconds','generation_after_bootstrap_seconds','generation_exchange_setup_seconds'):
                ratios=[];extra=[]
                for seed in env['seeds']:
                    case=next(c for c in cases if c['seed']==seed and c['config']['degree']==degree)
                    def cost(p):
                        rr=[r for r in case['records'] if r['policy']==p and
                            (metric!='generation_after_bootstrap_seconds' or not r['bootstrap'])]
                        v=sum(r['generation_seconds'] for r in rr)
                        if metric=='generation_exchange_setup_seconds':
                            v+=case['protocol_initialization_seconds'][p]
                            v+=sum(r['exchange_seconds'] for r in case['exchanges'] if r['policy']==p)
                        return v
                    a,b=cost(policy),cost(baseline);ratios.append(a/b);extra.append(a-b)
                row=dict(degree=degree,policy=policy,baseline=baseline,metric=metric,
                         median_ratio=st.median(ratios),median_extra_seconds=st.median(extra),
                         wins=sum(r<1 for r in ratios),per_seed_ratios=ratios)
                old=next(r for r in saved['paired'] if r['case_id']==f'm4096_d{degree}' and r['policy']==policy and r['baseline']==baseline and r['metric']==metric)
                assert abs(row['median_ratio']-old['median_ratio'])<1e-12
                assert abs(row['median_extra_seconds']+old['median_saved_seconds'])<1e-12
                independent.append(row)
    for filename,rows in (('width_summary.csv',width_rows),('width_pairs.csv',pairs)):
        with (HERE/filename).open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    width_medians=[]
    for degree in (1,4,8):
        for width in (512,2048):
            for policy,baseline in (('D','E'),('adaptive','static')):
                rr=[r for r in pairs if (r['degree'],r['width'],r['policy'],r['baseline'])==(degree,width,policy,baseline)]
                width_medians.append(dict(degree=degree,width=width,policy=policy,baseline=baseline,
                    median_ratio=st.median(r['generation_ratio'] for r in rr),
                    median_extra_seconds=st.median(r['extra_seconds'] for r in rr)))
    assets=sum(len(load_json(d/'prepared.json')['files']) for d in directories.values())
    audit=dict(case_count=9,policy_replays=36,record_count=sum(len(c['records']) for c in cases),
        validated_output_hashes=len(done['files']),validated_reference_hashes=len(load_json(Path(identity['reference'])/'completed.json')['file_hashes']),
        validated_prepared_assets=assets,validated_source_files=len(sources()),validated_core_files=len(source_hashes()),
        historical_training_digests_checked=9*200,historical_eval_records_checked=sum(len(c['quality']) for c in cases),
        relation_comparisons_recorded=done['relation_comparisons'],candidate_comparisons_recorded=done['candidate_membership_comparisons'],
        mismatches=0,paired=independent,width_medians=width_medians,state_matches=state_matches,
        limitations=['No new training or full oracle evaluation rerun: checks are saved records plus source-bound runtime assertions.',
                     'Full teacher/cache arrays are not saved, so recorded cache hashes are compared but not reconstructed.',
                     'Same-path timing differences are not policy benefits; three previously used seeds are exploratory.',
                     'Generation/codec replay timings are not end-to-end training or extra communication savings.'])
    (HERE/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k not in ('state_matches','limitations')},indent=2))


if __name__=='__main__':main()
