"""Read-only full-result audit with regenerated trace oracles and paired arithmetic."""
import json
from pathlib import Path
import sys
import tempfile
import statistics as st

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.public_scaling.data import sha,source_hashes
from experiments.public_scaling.util import load_json
from experiments.aggregator_recovery.run import Case,traces,check_case,own_sources,report

HERE=Path(__file__).parent


def main():
    output=ROOT/'experiments/aggregator_recovery/results_full'
    done=load_json(output/'completed.json');identity=load_json(output/'environment.json')
    assert identity['source_hashes']==own_sources()
    assert identity['core_source_hashes']==source_hashes()
    for name,h in done['files'].items():assert Path(name).name==name and sha(output/name)==h,name
    cases=[];rows=[];paired=[]
    for seed in identity['seeds']:
        for value in identity['plan']:
            cfg=Case(**value);_,trace=traces(cfg,seed)
            assert cfg.samples==4096 and cfg.rounds==200
            case=load_json(output/f'{cfg.name}_seed_{seed}.json')
            check_case(case,cfg,seed,identity,trace);cases.append(case)
            methods={m['policy']:m for m in case['methods']}
            # Byte identities are exact, not a statistical equivalence claim.
            if cfg.event!='handoff':assert methods['rebuild']['traffic']==methods['on_demand']['traffic']
            for p,m in methods.items():
                events=[r for r in m['round_records'] if r['event']]
                rows.append(dict(case=cfg.name,seed=seed,policy=p,total_bytes=m['traffic']['bytes'],
                    event_bytes=sum(r['traffic']['bytes'] for r in events),
                    replication_bytes=m['traffic'].get('replication_bytes',0),
                    local_seconds=m['setup_seconds']+sum(r['local_seconds'] for r in m['round_records']),
                    recovery_seconds=sum(r['recovery_seconds_including_abort'] for r in events),
                    max_array_bytes=max(r['persistent_array_bytes'] for r in m['round_records']),
                    events=len(events),replication_saved_vs_rebuild=methods['rebuild']['traffic']['bytes']-m['traffic']['bytes']))
    assert len(cases)==done['case_count']==18 and done['policy_replays']==54 and done['mismatches']==0
    assert sum(m['counts_comparisons'] for c in cases for m in c['methods'])==done['counts_comparisons']==592275456
    with tempfile.TemporaryDirectory(dir=HERE) as temporary:
        report(Path(temporary),cases)
        for name in ('report.md','summary.json','summary.csv'):
            assert (Path(temporary)/name).read_bytes()==(output/name).read_bytes(),name
    saved=load_json(output/'summary.json')
    metric_names=dict(total_bytes='total_bytes',event_bytes='event_round_bytes',local_seconds='local_seconds_with_setup',
                      recovery_seconds='recovery_seconds_with_aborted_attempts',max_array_bytes='max_persistent_array_bytes')
    for name in sorted({r['case'] for r in rows}):
        for policy in ('on_demand','hot_backup'):
            for metric in metric_names:
                ratios=[];extra=[]
                for seed in identity['seeds']:
                    a=next(r for r in rows if (r['case'],r['seed'],r['policy'])==(name,seed,policy))
                    b=next(r for r in rows if (r['case'],r['seed'],r['policy'])==(name,seed,'rebuild'))
                    extra.append(a[metric]-b[metric])
                    if b[metric]:ratios.append(a[metric]/b[metric])
                item=dict(case=name,policy=policy,metric=metric,median_ratio=None if not ratios else st.median(ratios),
                          median_extra=st.median(extra),wins=sum(v<1 for v in ratios),seed_count=len(ratios))
                original=next(r for r in saved['paired'] if r['case']==name and r['policy']==policy and r['metric']==metric_names[metric])
                assert item['median_ratio']==original['median_ratio'] and item['wins']==original['wins']
                paired.append(item)
    historical=load_json(ROOT/'experiments/graph_density/results_graph/environment.json')
    assert source_hashes()==historical['source_hashes']
    result=dict(case_count=18,policy_replays=54,round_records=sum(len(m['round_records']) for c in cases for m in c['methods']),
        validated_output_hashes=len(done['files']),validated_experiment_sources=len(own_sources()),
        unchanged_core_sources=len(source_hashes()),oracle_counts_compared=done['counts_comparisons'],mismatches=0,
        paired=paired,per_seed=rows,
        scope='Regenerated synthetic trace and saved target digest oracle; no full protocol or training rerun',
        limitations=['No actual network, training, model quality or failure detector/consensus validation.',
                     'Atomic commit and replica synchronization barriers exclude their own failures.',
                     'Event-round bytes include normal data, failed attempt, control and retry/replication; not pure handoff bytes.',
                     'Local processing times do not measure network recovery latency; arrays are persistent, not peak process memory.'])
    (HERE/'audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('per_seed','limitations')},indent=2))


if __name__=='__main__':main()
