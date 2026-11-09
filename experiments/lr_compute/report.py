"""Per-case, auditable report for the independent-process LR compute study."""
import csv
import json
from pathlib import Path

from experiments.public_lr_confirmation.design import verdict


def _write(path, rows):
    if rows:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with Path(path).open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            # Protocol snapshots omit unused counter keys in some cases.
            w.writerows({key: row.get(key, 0 if key.startswith('traffic_') else None)
                         for key in fields} for row in rows)


def _ratio(a, b):
    return a / b if b not in (None, 0) and a is not None else None


def reports(out, completed, memories, fixture=False):
    out = Path(out)
    rows, groups = [], {}
    for meta, r in completed:
        m = meta['method']
        s = r['summary'][m]
        p = r['preparation']
        phases = {k + '_seconds': s[k + '_seconds'] for k in ('private', 'generation', 'exchange', 'public')}
        traffic = s['traffic']
        total = s['with_shared_preparation_seconds']
        row = dict(**meta, head_pipeline_seconds=s['head_pipeline_seconds'], **phases,
            generation_fraction=s['generation_fraction'], teacher_recompute_fraction=s['teacher_recompute_fraction'],
            teacher_forward_endpoints=sum(x['teacher_forward_endpoints'] for x in r['round_records']),
            student_forward_endpoints=sum(x['student_forward_endpoints'] for x in r['round_records']),
            certified_edges_before_refresh=sum(x['certified_edges_before_refresh'] for x in r['round_records']),
            private_optimizer_steps=sum(x['private_optimizer_steps'] for x in r['round_records']),
            public_optimizer_steps=sum(x['public_optimizer_steps'] for x in r['round_records']),
            process_peak_bytes=r['process_peak_bytes'], persistent_method_array_bytes=s['persistent_method_array_bytes'],
            initial_traffic_total_bytes=s['initial_traffic']['total_bytes'], traffic_total_bytes=traffic['total_bytes'],
            traffic=dict(traffic), base_preparation_seconds=p['base_seconds'],
            additional_preparation_seconds_raw=p['additional_seconds_raw'],
            additional_preparation_seconds=p['additional_seconds'], known_preparation_contamination=p['known_contamination'],
            preparation_reason=p['reason'], shared_loading_seconds=r['shared_loading_seconds'], total_with_shared_preparation_seconds=total,
            final_acc=s['final_metrics']['mean']['acc'], final_nmi=s['final_metrics']['mean']['nmi'],
            final_ari=s['final_metrics']['mean']['ari'])
        # Flatten traffic fields for convenient CSV analysis.
        row.update({'traffic_' + k: v for k, v in traffic.items() if k != 'total_bytes'})
        row.pop('traffic')
        rows.append(row)
        groups.setdefault(meta['case_id'], {})[m] = (meta, r, row)

    pairs, quality = [], []
    for cid, g in sorted(groups.items()):
        if set(g) != {'B', 'E', 'D'}:
            raise ValueError('Incomplete method triple: ' + cid)
        bm, br, b = g['B']
        for ref in ('B', 'E'):
            dm, dr, d = g['D']
            reason = ''
            if d['total_with_shared_preparation_seconds'] is None or g[ref][2]['total_with_shared_preparation_seconds'] is None:
                reason = 'Known contaminated preparation makes preparation-inclusive total unavailable'
            pairs.append(dict(case_id=cid, family=bm['family'], seed=bm['seed'], partition=bm['partition'], role=bm['role'],
                comparison='D/' + ref, head_ratio=_ratio(d['head_pipeline_seconds'], g[ref][2]['head_pipeline_seconds']),
                head_saved_seconds=g[ref][2]['head_pipeline_seconds']-d['head_pipeline_seconds'],
                generation_ratio=_ratio(d['generation_seconds'], g[ref][2]['generation_seconds']),
                total_ratio=_ratio(d['total_with_shared_preparation_seconds'], g[ref][2]['total_with_shared_preparation_seconds']),
                total_ratio_unavailable_reason=reason,
                traffic_equal=d['traffic_total_bytes']==g[ref][2]['traffic_total_bytes'],
                initial_traffic_equal=d['initial_traffic_total_bytes']==g[ref][2]['initial_traffic_total_bytes'],
                traffic_ratio=_ratio(d['traffic_total_bytes'],g[ref][2]['traffic_total_bytes'])))
        v = verdict(br)
        observed = [x for x in br['metrics'] if x['round'] >= 20]
        final_clients_b = br['metrics'][-1]['clients']
        final_single = sum(c['occupied_clusters'] == 1 for c in final_clients_b)
        final_near99 = sum(c['largest_cluster_fraction'] >= .99 for c in final_clients_b)
        quality.append(dict(case_id=cid, family=bm['family'], seed=bm['seed'], partition=bm['partition'], role=bm['role'],
            baseline='B', **v, final_single_clients=final_single, final_near99_clients=final_near99,
            mean_largest_cluster_fraction=sum(c['largest_cluster_fraction'] for c in final_clients_b)/len(final_clients_b),
            final_acc=b['final_acc'], final_nmi=b['final_nmi'], final_ari=b['final_ari'],
            process_guard_vacuous=(len(observed) == 0), formal_claim=(not fixture and bm['role'] != 'development'),
            early_phase_caveat='Final verdict only; early phase changes are descriptive'))

    clients, events = [], []
    step = 1 if fixture else 20
    for meta, r in completed:
        m = meta['method']
        for checkpoint in r['metrics']:
            if checkpoint['round'] % step and checkpoint['round'] != r['metrics'][-1]['round']:
                continue
            for c in checkpoint['clients']:
                common = dict(**meta, round=checkpoint['round'], client=c['client'], width=c['width'], acc=c['acc'],
                    nmi=c['nmi'], ari=c['ari'], occupied_clusters=c['occupied_clusters'],
                    largest_cluster_fraction=c['largest_cluster_fraction'])
                clients.append(common)
                events.append(dict(**common, single_cluster=c['occupied_clusters']==1,
                    largest_cluster_at_least_099=c['largest_cluster_fraction']>=.99))
    finals = {}
    for e in clients:
        k=(e['case_id'],e['method']); finals[k]=max(finals.get(k,-1),e['round'])
    final_clients=[e for e in clients if e['round']==finals[(e['case_id'],e['method'])]]
    memory=[]
    for meta,r in memories:
        m=meta['method']; s=r['summary'][m]
        memory.append(dict(**meta,process_peak_bytes=r['process_peak_bytes'],persistent_method_array_bytes=s['persistent_method_array_bytes'],
            scope='Standalone process; no oracle/evaluation; two selected cases only'))
    _write(out/'runs.csv',rows); _write(out/'paired_cost.csv',pairs); _write(out/'quality.csv',quality)
    flagged_events=[e for e in events if e['single_cluster'] or e['largest_cluster_at_least_099']]
    _write(out/'final_clients.csv',final_clients); _write(out/'events.csv',flagged_events); _write(out/'memory.csv',memory)
    summary=dict(fixture=fixture,runs=len(rows),memory_runs=len(memory),cases=len(groups),paired_comparisons=len(pairs))
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# P1 LR compute report','',f"{'Synthetic smoke fixture' if fixture else 'LR .05 confirmation inputs'}; {len(rows)} timed runs; {len(memory)} standalone memory runs.",'',
        '## Per-case paired costs','',
        '| Case | Family | Seed | Partition | Role | D/B head | D/B saved s | D/B gen | D/B total | D/E head | D/E saved s | D/E gen | D/E total | Traffic equal |','|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|']
    by={(x['case_id'],x['comparison']):x for x in pairs}
    for cid,g in sorted(groups.items()):
        meta=g['B'][0]; x=by[cid,'D/B']; y=by[cid,'D/E']
        fmt=lambda v:'NA' if v is None else f'{v:.4f}'
        lines.append(f"| {cid} | {meta['family']} | {meta['seed']} | {meta['partition']} | {meta['role']} | {fmt(x['head_ratio'])} | {fmt(x['head_saved_seconds'])} | {fmt(x['generation_ratio'])} | {fmt(x['total_ratio'])} | {fmt(y['head_ratio'])} | {fmt(y['head_saved_seconds'])} | {fmt(y['generation_ratio'])} | {fmt(y['total_ratio'])} | {x['traffic_equal'] and y['traffic_equal']} |")
    lines += ['', 'Costs use C0 + additional preparation + shared loading + measured head pipeline. Preparation is reused input work but shown as a comparable reference; timing is exploratory single-process measurement and not a P2 parallel-runtime estimate. K64 seed1002 preparation is marked NA where the recorded historical sleep contamination applies; raw value and reason remain in runs.csv and paired_cost.csv.', '',
        '## Quality guard','', 'The baseline B final result is evaluated with the predeclared LR-confirmation verdict, including final structure, post-round-20 process guard, and NMI floor. Smoke rows are development only; with 12 rounds the post-round-20 process guard is vacuous and no formal pass claim is made. Per-client checkpoints and final client metrics are reported separately; early phase movement is descriptive and does not replace the final guard.', '',
        '| Case | Role | Predeclared pass | Final near-99 clients | Mean largest-cluster fraction |', '|---|---|---|---:|---:|']
    for q in quality:
        lines.append(f"| {q['case_id']} | {q['role']} | {q['passed'] if q['formal_claim'] else 'development only'} | {q['final_near99_clients']} | {q['mean_largest_cluster_fraction']:.4f} |")
    lines += ['', '## Memory scope','', 'Standalone memory results cover only two selected cases and exclude oracle and evaluation work. Peak process memory includes interpreter and input preparation/loading; persistent method arrays are also listed. These limited cases do not support broad memory scaling claims.', '',
        'All eight full-design case/seed rows are retained independently with role labels; no pooling across seeds or roles. Smoke mode has 12 timed runs and 6 memory runs and exercises the report path only. events.csv contains only flagged client/checkpoint rows; final client metrics are in final_clients.csv. Exact serialized traffic and endpoint counts are reported in runs.csv; traffic equality is checked per paired case.', '']
    (out/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return summary
