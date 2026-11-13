"""Audit stored formal results without training or modifying originals."""
import copy,json,statistics
from pathlib import Path
from experiments.local_public_lr_confirmation import run,report

H=Path(__file__).resolve().parent;D=run.DIR/'results_full'


def main():
    env=run.read(D/'environment.json');run.check_environment(env);run._verify_finished(D)
    assert not env['fixture'] and env['preset']=='full'
    snap,refs,history=run._history_snapshot(env,True)
    assert snap==env['historical_sources']
    shadow=copy.deepcopy(env);run.prepare_inputs(shadow,H/'input_recheck');assert shadow==env
    records=[];analyses={}
    for meta in env['schedule']:
        r=run.read(D/'runs'/run.filename(meta));entry=env['inputs'][meta['case_id']]
        run.verify_record(r,meta,run.plan('full')['local_lr'],entry,False)
        assert all(r[k]==refs[meta['case_id']][k] for k in ('initial_head_digest','graph_sha256'))
        records.append((meta,r))
        by={m['round']:m for m in r['metrics']}
        late=[dict(round=t,**c) for t in (160,180,200) for c in by[t]['clients']]
        severe=lambda c:c['occupied_clusters']<=1 or c['largest_cluster_fraction']>=.99
        assert len(late)==18 and all(not severe(c) for c in late)
        context={}
        for branch,old in [('baseline',refs[meta['case_id']])]+[(b,history['low_capacity'][(meta['case_id'],b)]) for b in ('low_lr','private_only')]:
            context[branch]=dict(late_pass=report.recovery(old)['passed'],final_clients=old['metrics'][-1]['clients'])
        effects={}
        for label,lo,hi in [('early',1,40),('late',160,200)]:
            cs=[c for o in r['diagnostic_records'] if lo<=o['round']<=hi for c in o['clients'] if c['client'] in (0,3)]
            effects[label]=dict(client_rounds=len(cs),private_fit_change=statistics.mean(c['T1']['private']['fixed_pseudo_fit']-c['T0']['private']['fixed_pseudo_fit'] for c in cs),
                public_fit_change=statistics.mean(c['T2']['private']['fixed_pseudo_fit']-c['T1']['private']['fixed_pseudo_fit'] for c in cs),
                public_probe_concentration_change=statistics.mean(c['T2']['public']['largest_cluster_fraction']-c['T1']['public']['largest_cluster_fraction'] for c in cs))
        analyses[meta['case_id']]=dict(late_pass=True,late_clients=late,final_clients=r['metrics'][-1]['clients'],
            severe_test_events=[dict(round=m['round'],**c) for m in r['metrics'] for c in m['clients'] if severe(c)],
            healthy_test_checkpoints={str(i):[m['round'] for m in r['metrics'] if not severe(m['clients'][i])] for i in (0,3)},
            effects=effects,history=context,worker_power={k:r[k]['ac_line_status'] for k in ('worker_started_power','worker_ended_power')})
    regenerated=H/'regenerated';report.reports(regenerated,records,refs,fixture=False,history=history)
    files=[p for p in regenerated.iterdir() if p.is_file()];assert all(run.digest(p)==run.digest(D/p.name) for p in files)
    power=[json.loads(l) for p in D.glob('power_*.jsonl') for l in p.read_text().splitlines()]
    completed=run.read(D/'completed.json')
    audit=dict(formal_runs=3,rounds_each=200,confirmed_cases=3,client_checkpoint_passes=54,expected_client_checkpoint_checks=54,
        completion_manifest_files=len(completed['files']),sources=len(env['sources']),all_record_validations=True,historical_inputs_and_manifests_unchanged=True,
        regenerated_reports_byte_equal=len(files),power=dict(samples=len(power),ac_samples=sum(p['ac_line_status']==1 for p in power),battery_samples=sum(p['ac_line_status']==0 for p in power),gap_warnings=sum(p['gap_warning'] for p in power)),
        timing_evidence_used=False,execution_policy='Quality-only execution under amended startup policy; performance measurements are not used.',analyses=analyses)
    (H/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='analyses'},indent=2))
    for cid,a in analyses.items():
        print(cid,'late small',[(x['round'],x['client'],x['occupied_clusters'],round(x['largest_cluster_fraction']*100,4),round(x['nmi'],5)) for x in a['late_clients'] if x['client'] in (0,3)])
        print('healthy checks',a['healthy_test_checkpoints'],'event_count',len(a['severe_test_events']),'effects',a['effects'])
        print('history final small', {b:[(c['client'],round(c['largest_cluster_fraction']*100,4),round(c['nmi'],5)) for c in x['final_clients'] if c['client'] in (0,3)] for b,x in a['history'].items()})


if __name__=='__main__':main()
