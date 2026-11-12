from pathlib import Path
import csv,json


def recovery(record, checkpoints=(160,180,200)):
    by_round={m['round']:m for m in record.get('metrics',[])}
    capacity={c['client']:c['private_capacity'] for c in record.get('initial_diagnostics',{}).get('clients',[])}
    details=[]
    for rnd in checkpoints:
        clients={c['client']:c for c in by_round.get(rnd,{}).get('clients',[])}
        for client in range(6):
            c=clients.get(client)
            ok=c is not None and c['occupied_clusters']>1 and c['largest_cluster_fraction']<.99
            details.append(dict(round=rnd,client=client,capacity=capacity.get(client,100 if client in (0,3) else (400 if client in (1,4) else 700)),
                present=c is not None,passed=ok,occupied_clusters=None if c is None else c['occupied_clusters'],
                largest_cluster_fraction=None if c is None else c['largest_cluster_fraction'],nmi=None if c is None else c['nmi']))
    return dict(passed=all(x['passed'] for x in details),client_results={str(c):all(x['passed'] for x in details if x['client']==c) for c in range(6)},details=details)


def write_csv(path,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)


def reports(out,completed,references,fixture=False):
    out=Path(out);checkpoints=(1,2,3) if fixture else (160,180,200)
    recovery_rows=[];stage_rows=[];event_rows=[];loss_rows=[];initial_rows=[];test_rows=[];summary=[];history=[]
    for meta,r in completed:
        identity={k:meta[k] for k in ('case_id','seed','partition','branch')}
        for c in r['initial_diagnostics']['clients']:
            initial_rows.append(dict(**identity,client=c['client'],capacity=c['private_capacity'],pseudo_histogram=json.dumps(c['fixed_pseudo_histogram']),
                private_prediction=json.dumps(c.get('private_prediction')),public_prediction=json.dumps(c.get('public_probe_prediction'))))
        for obs in r['diagnostic_records']:
            rnd=obs['round']
            for c in obs['clients']:
                for stage in ('T0','T1','T2'):
                    for domain in ('private','public'):
                        v=c[stage][domain];row=dict(**identity,round=rnd,client=c['client'],stage=stage,domain=domain,
                            counts=json.dumps(v['counts']),occupied_clusters=v['occupied_clusters'],largest_cluster_fraction=v['largest_cluster_fraction'],
                            sample_count=v['sample_count'],fixed_pseudo_fit=v.get('fixed_pseudo_fit'))
                        stage_rows.append(row)
                        if v['occupied_clusters']==1 or v['largest_cluster_fraction']>=.99:event_rows.append(row)
                loss_rows.append(dict(**identity,round=rnd,client=c['client'],private_update_loss=c['private_update_loss'],public_update_loss=c['public_update_loss'],
                    positive_relation_fraction_T1=c['positive_relation_fraction_T1'],
                    teacher_relation_sha256_T1=c['teacher_relation_sha256_T1'],private_order_sha256=json.dumps(c['private_order_sha256']),public_order_sha256=c['public_order_sha256'],
                    private_weight_l2=c['T1']['private_update_delta']['weight_l2'],private_bias_l2=c['T1']['private_update_delta']['bias_l2'],private_parameter_l2=c['T1']['private_update_delta']['parameter_l2'],
                    public_weight_l2=c['T2']['public_update_delta']['weight_l2'],public_bias_l2=c['T2']['public_update_delta']['bias_l2'],public_parameter_l2=c['T2']['public_update_delta']['parameter_l2']))
        for m in r['metrics']:
            for c in m['clients']:test_rows.append(dict(**identity,round=m['round'],**c))
        if meta['branch']=='baseline':
            status='short_replay_only';passed=None
        else:
            result=recovery(r,checkpoints);passed=result['passed'];status='released_severe_collapse' if passed else 'not_released'
            for d in result['details']:recovery_rows.append(dict(**identity,**d))
        summary.append(dict(**identity,recovery_status=status,passed=passed,rounds=r['config']['rounds'],probe_seconds=r['summary']['B']['probe_seconds'],
            evaluation_seconds=r['validation']['evaluation_seconds_excluded'],worker_wall_seconds=r.get('engine_wall_seconds')))
    for case_id,old in references.items():
        for m in old['metrics']:
            for c in m['clients']:history.append(dict(case_id=case_id,source='historical_existing_test_metrics',round=m['round'],**c))
    for name,rows in [('initial.csv',initial_rows),('stages.csv',stage_rows),('stage_events.csv',event_rows),('losses_and_deltas.csv',loss_rows),('test_checkpoints.csv',test_rows),('recovery.csv',recovery_rows),('runs.csv',summary),('historical_test_metrics.csv',history)]:write_csv(out/name,rows)
    compact=[row for row in stage_rows if row['round']<=20 or row['round']%20==0 or row['round'] in checkpoints]
    write_csv(out/'stage_display.csv',compact)
    verdict={branch:dict(passed=sum(x['passed'] is True for x in summary if x['branch']==branch),cases=sum(x['branch']==branch for x in summary)) for branch in ('private_only','low_lr')}
    (out/'summary.json').write_text(json.dumps(dict(fixture=fixture,verdict=verdict,comparison_checkpoints=checkpoints,runs=summary,
        note='Diagnostic study only; no certification speedup claims. Historical unrecorded stage fields are NA.'),indent=2),encoding='utf-8')
    lines=['# Low-capacity stability diagnostic report','',f"{'Synthetic smoke; no scientific outcome' if fixture else 'Official STL-10 diagnostic'}; {len(completed)} runs. No performance conclusions.",'',
        '|Case|Branch|Rounds|Recovery check|','|---|---|---:|---|']
    for x in summary:lines.append(f"|{x['case_id']}|{x['branch']}|{x['rounds']}|{x['recovery_status']}|")
    lines+=['','## Interpretation','',
        'Baseline is a short exact replay and does not supply unrecorded historical T0/T1/T2 data at rounds 160/180/200. Those historical fields are NA. Existing historical test metrics are retained separately.',
        'T0 precedes private SGD, T1 follows private SGD and is the actual teacher snapshot, T2 follows public SGD. Private-only runs no public gradient/update; its T2 equals T1. Probe snapshots and independent RNG stream must not affect training.',
        'Every specified checkpoint and all six clients must pass: at least two occupied clusters and largest fraction below 0.99. Passing means release of severe collapse only; no ACC gain or new NMI threshold. Full process events remain in stage/test logs.',
        'All-client lower public LR changes both local steps and future teacher feedback. Outcomes cannot identify one unique cause. Diagnostic timing includes instrumentation effects and must not be pooled with historical certification benchmarks.','']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
