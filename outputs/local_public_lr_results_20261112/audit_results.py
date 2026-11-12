"""Read-only audit of formal runs; writes only this review directory."""
from pathlib import Path
import copy, json, statistics
from experiments.local_public_lr import run, report

ROOT=run.ROOT
OUT=Path(__file__).resolve().parent
RESULT=ROOT/'experiments/local_public_lr/results_full'


def severe(c):
    return c['occupied_clusters']<=1 or c['largest_cluster_fraction']>=.99


def main():
    env=run.read(RESULT/'environment.json');run.check_environment(env)
    complete=run.read(RESULT/'completed.json')
    for name,sha in complete['files'].items():
        assert run.digest(RESULT/name)==sha,name
    assert run.read(RESULT/'finished.json')['completed_manifest_sha256']==run.digest(RESULT/'completed.json')
    assert env['preset']=='full' and not env['fixture'] and len(env['schedule'])==2
    shadow=copy.deepcopy(env)
    refs=run.prepare_inputs(shadow,OUT/'input_recheck')
    history=run.prepare_history(shadow,OUT/'input_recheck')
    assert shadow==env,'Frozen reference/input identity changed'
    records=[]
    for meta in env['schedule']:
        r=run.read(RESULT/'runs'/run.filename(meta))
        run.verify_record(r,meta,run.plan('full')[meta['branch']],env['inputs'][meta['case_id']],False)
        if meta['branch']=='baseline':run.baseline_compare(r,refs[meta['case_id']])
        else:
            ref=refs[meta['case_id']]
            assert all(r[k]==ref[k] for k in ('initial_head_digest','graph_sha256'))
        records.append((meta,r))
    regenerated=OUT/'regenerated'
    report.reports(regenerated,records,refs,fixture=False,history=history)
    generated=[p for p in regenerated.iterdir() if p.is_file()]
    assert all(run.digest(p)==run.digest(RESULT/p.name) for p in generated)
    all_runs={m['branch']:r for m,r in records};all_runs.update(history)
    analyses={}
    for branch,r in all_runs.items():
        late=[dict(round=m['round'],**c) for m in r['metrics'] if m['round'] in (160,180,200) for c in m['clients']]
        assert len(late)==18
        manual_pass=all(not severe(c) for c in late)
        assert manual_pass==report.recovery(r)['passed']
        events=[dict(round=m['round'],client=c['client'],occupied=c['occupied_clusters'],maximum=c['largest_cluster_fraction'])
                for m in r['metrics'] for c in m['clients'] if severe(c)]
        periods={}
        for name,lo,hi in (('early',1,40),('late',160,200)):
            small=[c for d in r['diagnostic_records'] if lo<=d['round']<=hi for c in d['clients'] if c['client'] in (0,3)]
            periods[name]=dict(client_rounds=len(small),
                private_fit_change=statistics.mean(c['T1']['private']['fixed_pseudo_fit']-c['T0']['private']['fixed_pseudo_fit'] for c in small),
                public_fit_change=statistics.mean(c['T2']['private']['fixed_pseudo_fit']-c['T1']['private']['fixed_pseudo_fit'] for c in small),
                public_probe_concentration_change=statistics.mean(c['T2']['public']['largest_cluster_fraction']-c['T1']['public']['largest_cluster_fraction'] for c in small))
        analyses[branch]=dict(late_pass=manual_pass,late_small=[c for c in late if c['client'] in (0,3)],
            final_clients=r['metrics'][-1]['clients'],test_severe_events=events,stage_changes=periods)
    base,local=all_runs['baseline'],all_runs['local_lr']
    first=[]
    for b,l in zip(base['diagnostic_records'][0]['clients'],local['diagnostic_records'][0]['clients']):
        assert b['T0']==l['T0'] and b['T1']==l['T1']
        changed=b['T2']['head_digest']!=l['T2']['head_digest']
        assert changed==(b['client'] in (0,3))
        first.append(dict(client=b['client'],public_head_changed=changed))
    for bd,ld in zip(base['diagnostic_records'],local['diagnostic_records']):
        assert all(b['private_order_sha256']==l['private_order_sha256'] and b['public_order_sha256']==l['public_order_sha256'] for b,l in zip(bd['clients'],ld['clients']))
    power=[json.loads(line) for p in RESULT.glob('power_*.jsonl') for line in p.read_text().splitlines()]
    audit=dict(manifest_files=len(complete['files']),source_files=len(env['sources']),formal_runs=2,rounds_each=200,
        baseline_all_200_non_time_rounds_and_checkpoints_equal=True,records_verified=True,
        unchanged_inputs_and_historical_manifests=True,regenerated_reports_byte_equal=len(generated),
        first_round_intervention=first,all_private_and_public_orders_equal=True,
        power=dict(samples=len(power),all_ac=all(p['ac_line_status']==1 for p in power),gap_warnings=sum(p['gap_warning'] for p in power)),
        analyses=analyses)
    (OUT/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='analyses'},indent=2))
    for branch,a in analyses.items():
        print(branch,'pass=',a['late_pass'],'test_events=',a['test_severe_events'])
        print('late small:',[(c['round'],c['client'],c['occupied_clusters'],round(c['largest_cluster_fraction']*100,4),round(c['nmi'],5)) for c in a['late_small']])
        print('final others:',[(c['client'],c['occupied_clusters'],round(c['largest_cluster_fraction']*100,4),round(c['nmi'],5)) for c in a['final_clients'] if c['client'] not in (0,3)])
        print('stages:',a['stage_changes'])


if __name__=='__main__':main()
