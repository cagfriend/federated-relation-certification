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


def reports(out,completed,references,fixture=False,history=None):
    out=Path(out);checkpoints=(1,2,3) if fixture else (160,180,200)
    out.mkdir(parents=True,exist_ok=True)
    # Reports may also be regenerated directly: do not assert a replay gate
    # merely because this function was called outside the validated runner.
    for meta,r in completed:
        if meta['branch']=='baseline':
            reference=references[meta['case_id']]
            strip=lambda rows:[{k:v for k,v in row.items() if not k.endswith('_seconds')} for row in rows]
            if any(r[k]!=reference[k] for k in ('initial_head_digest','graph_sha256')) or strip(r['round_records'])!=strip(reference['round_records'][:r['config']['rounds']]):
                raise ValueError('Cannot report an unverified baseline replay')
            by_round={m['round']:m for m in reference['metrics']}
            if any(m!=by_round.get(m['round']) for m in r['metrics']):raise ValueError('Baseline metric replay failed')
    recovery_rows=[];stage_rows=[];event_rows=[];loss_rows=[];initial_rows=[];test_rows=[];summary=[];history_rows=[]
    history_runs=history or {}
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
        result=recovery(r,checkpoints);passed=result['passed'];status='released_severe_collapse' if passed else 'not_released'
        for d in result['details']:recovery_rows.append(dict(**identity,**d))
        summary.append(dict(**identity,recovery_status=status,passed=passed,rounds=r['config']['rounds'],probe_seconds=r['summary']['B']['probe_seconds'],
            evaluation_seconds=r['validation']['evaluation_seconds_excluded'],worker_wall_seconds=r.get('engine_wall_seconds')))
    for case_id,old in references.items():
        for m in old['metrics']:
            for c in m['clients']:history_rows.append(dict(case_id=case_id,source='historical_existing_test_metrics',round=m['round'],**c))
    for name,rows in [('initial.csv',initial_rows),('stages.csv',stage_rows),('stage_events.csv',event_rows),('losses_and_deltas.csv',loss_rows),('test_checkpoints.csv',test_rows),('recovery.csv',recovery_rows),('runs.csv',summary),('historical_test_metrics.csv',history_rows)]:write_csv(out/name,rows)
    compact=[row for row in stage_rows if row['round']<=20 or row['round']%20==0 or row['round'] in checkpoints]
    write_csv(out/'stage_display.csv',compact)
    verdict={branch:dict(passed=sum(x['passed'] is True for x in summary if x['branch']==branch),cases=sum(x['branch']==branch for x in summary)) for branch in ('baseline','local_lr')}
    (out/'summary.json').write_text(json.dumps(dict(fixture=fixture,verdict=verdict,comparison_checkpoints=checkpoints,runs=summary,
        note='Single-case local LR diagnostic; no certification speedup or general healthy-clustering claims.'),indent=2),encoding='utf-8')
    all_records={meta['branch']:r for meta,r in completed}
    all_records.update(history_runs)
    rates=[];effects=[];contrasts=[];late=[]
    for branch,r in all_records.items():
        weights=r.get('public_client_weights',[r['config']['public_weight']]*6)
        for c,w in enumerate(weights):
            rates.append(dict(branch=branch,client=c,public_weight=w,public_update_active=branch!='private_only',
                              configured_effective_public_lr=r['config']['head_lr']*w,
                              effective_public_lr=0.0 if branch=='private_only' else r['config']['head_lr']*w,
                              source='historical' if branch in (history_runs) else 'new_run'))
        for d in r['diagnostic_records']:
            for c in d['clients']:
                before,private,public=(c[k] for k in ('T0','T1','T2'))
                effects.append(dict(branch=branch,round=d['round'],client=c['client'],
                    private_fit_change=private['private']['fixed_pseudo_fit']-before['private']['fixed_pseudo_fit'],
                    public_fit_change=public['private']['fixed_pseudo_fit']-private['private']['fixed_pseudo_fit'],
                    private_probe_concentration_change=private['public']['largest_cluster_fraction']-before['public']['largest_cluster_fraction'],
                    public_probe_concentration_change=public['public']['largest_cluster_fraction']-private['public']['largest_cluster_fraction'],
                    public_parameter_l2=public['public_update_delta']['parameter_l2'],
                    positive_relation_fraction_T1=c['positive_relation_fraction_T1']))
        rec=recovery(r,checkpoints)
        for d in rec['details']:late.append(dict(branch=branch,source='historical' if branch in (history_runs) else 'new_run',**d))
    by={(e['branch'],e['round'],e['client']):e for e in effects}
    for e in effects:
        if e['branch']=='baseline':continue
        b=by.get(('baseline',e['round'],e['client']))
        if b is None:continue
        contrasts.append(dict(branch=e['branch'],reference='baseline',round=e['round'],client=e['client'],
                              **{k+'_difference':e[k]-b[k] for k in e if k not in ('branch','round','client')}))
    write_csv(out/'client_rates.csv',rates);write_csv(out/'stage_effects.csv',effects)
    write_csv(out/'stage_contrasts.csv',contrasts);write_csv(out/'late_comparison.csv',late)
    hist_test=[]
    for branch,r in (history_runs).items():
        for m in r['metrics']:
            for c in m['clients']:hist_test.append(dict(branch=branch,round=m['round'],**c))
    write_csv(out/'historical_diagnostic_checkpoints.csv',hist_test)
    summary_path=out/'summary.json';document=json.loads(summary_path.read_text(encoding='utf-8'))
    document['historical_reference_recovery']={b:recovery(r,checkpoints) for b,r in (history_runs).items()}
    document['baseline_exact_replay']=True
    document['interpretation']='Release of severe collapse only; local intervention still changes future coupled teachers.'
    summary_path.write_text(json.dumps(document,indent=2),encoding='utf-8')
    lines=['# Local public-LR diagnostic report','',
        'Synthetic smoke only; no scientific outcome.' if fixture else 'Single frozen STL-10 case: strong / IID / seed1001.',
        '', 'Two new full-length B trajectories; baseline passed the exact historical training replay gate. No performance conclusions.', '',
        '|Branch|Rounds|Severe-collapse check|','|---|---:|---|']
    for x in summary:lines.append(f"|{x['branch']}|{x['rounds']}|{x['recovery_status']}|")
    lines+=['','Baseline: all clients effective public LR 0.05. Local intervention: clients 0/3 use 0.0125; others retain 0.05. Both use two public steps. Actual client weights/rates are in client_rates.csv.',
        '', 'Recovery is checked for all six clients at every prescribed late checkpoint: occupied clusters > 1 and maximum cluster fraction < 0.99. Missing values fail. This is release of severe collapse, not sufficient semantic health; no ACC improvement criterion.',
        '', 'late_comparison.csv lists every late client/checkpoint, including historical all-client low-LR and private-only references when available. stage_effects.csv records within-round changes; stage_contrasts.csv subtracts the matched new baseline, not independent causal effects.',
        '', 'T0 precedes private SGD; T1 is the actual teacher after private SGD; T2 follows public SGD. Baseline and local_lr both have real 200-round instrumentation. Historical test fields are exported separately; unrecorded fields are never reconstructed.',
        '', 'Lowering only local learning rates still changes later coupled teacher feedback. A single configuration cannot establish a unique cause or generalize to non-IID. Diagnostic time is not certification speedup evidence.', '']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
