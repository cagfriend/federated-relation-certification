"""Build flat diagnostics and a descriptive report from completed runs."""
import csv
import json
from pathlib import Path

import numpy as np


def _write_csv(path, rows):
    rows = list(rows)
    if not rows:
        path.write_text('', encoding='utf-8')
        return
    keys = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)


def _load_runs(out):
    paths = sorted((Path(out) / 'runs').glob('*.json'))
    runs = []
    for path in paths:
        run = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(run.get('case'), dict) or not isinstance(run.get('diagnostics'), list):
            continue
        runs.append(run)
    if not runs:
        raise FileNotFoundError(f'no completed run JSON files in {Path(out) / "runs"}')
    return runs


def _diag_rows(run):
    case = run['case']
    result = []
    for event in run.get('diagnostics', []):
        for client in event.get('clients', []):
            row = dict(partition=case['partition'], setting=case['setting'],
                       round=event.get('round'), stage=event.get('stage'), client=client.get('client'),
                       teacher_positive_rate=(event.get('teacher_positive_rates') or [None] * (client.get('client', 0) + 1))[client.get('client', 0)]
                       if event.get('teacher_positive_rates') and client.get('client', 0) < len(event['teacher_positive_rates']) else None)
            for split in ('private', 'public'):
                metrics = client.get(split) or {}
                for key, value in metrics.items():
                    row[f'{split}_{key}'] = json.dumps(value, separators=(',', ':')) if isinstance(value, (list, dict)) else value
            target = event.get('committed_target')
            if target:
                for key, value in target.items(): row[f'committed_{key}'] = json.dumps(value) if isinstance(value, (list, dict)) else value
            result.append(row)
    return result


def _quality_rows(run):
    rows = []
    for evaluation in run.get('evaluations', []):
        for client in evaluation.get('clients', []):
            native = client.get('native_head') or {}
            row = dict(partition=run['case']['partition'], setting=run['case']['setting'],
                       round=evaluation.get('round'), client=client.get('client'))
            for key, value in native.items():
                row[f'native_{key}'] = json.dumps(value, separators=(',', ':')) if isinstance(value, (list, dict)) else value
            conf = client.get('native_confidence') or {}
            for key, value in conf.items():
                row[f'confidence_{key}'] = json.dumps(value, separators=(',', ':')) if isinstance(value, (list, dict)) else value
            for key, value in client.items():
                if key not in ('client', 'native_head', 'native_confidence'):
                    row[f'kmeans_{key}'] = json.dumps(value, separators=(',', ':')) if isinstance(value, (list, dict)) else value
            rows.append(row)
    return rows


def build(out):
    out = Path(out)
    runs = _load_runs(out)
    diagnostics = [row for run in runs for row in _diag_rows(run)]
    quality = [row for run in runs for row in _quality_rows(run)]
    _write_csv(out / 'diagnostics.csv', diagnostics)
    _write_csv(out / 'test_quality.csv', quality)

    summary_runs = []
    report_lines = ['# Early cluster guard: staircase exploration', '',
                    'Descriptive results for the observed trajectories. No new pass threshold is applied.', '']
    for run in runs:
        case = run['case']; label = f"{case['partition']} / {case['setting']}"
        events = run.get('diagnostics', [])
        t2 = [e for e in events if e.get('stage') == 'T2']
        last50 = t2[-50:]
        per_client = []
        for client in range(len(run.get('initial_checks', []))):
            cm = [c.get('private', {}) for e in last50 for c in e.get('clients', []) if c.get('client') == client]
            per_client.append(dict(client=client,
                last50_private_max_cluster_mean=float(np.mean([m['largest'] for m in cm])) if cm else None,
                last50_private_empty_clusters_mean=float(np.mean([m['empty'] for m in cm])) if cm else None,
                last50_private_entropy_mean=float(np.mean([m['entropy_mean'] for m in cm])) if cm else None))
            pm=[c.get('public',{}) for e in last50 for c in e.get('clients',[]) if c.get('client')==client]
            per_client[-1].update({f'last50_public_{key}_mean':float(np.mean([m[key] for m in pm])) if pm else None for key in ('largest','empty','entropy_mean')})
        native_rows = [q for q in run.get('evaluations', []) if q.get('round') == max((x.get('round', 0) for x in run.get('evaluations', [])), default=0)]
        native = [c.get('native_head', {}) for e in native_rows for c in e.get('clients', [])]
        max_events = []
        for e in events:
            for c in e.get('clients', []):
                for split in ('private', 'public'):
                    m = c.get(split) or {}
                    if m.get('largest', 0) >= .99:
                        max_events.append(dict(round=e.get('round'), stage=e.get('stage'), client=c.get('client'), split=split, largest=m['largest']))
        s = dict(case=case, setup=run.get('setup'), probe_seconds=run.get('probe_seconds'),
                 rows=run.get('rows', []), single_or_max_99_events=max_events,
                 last50_T2_private_by_client=per_client,
                 test_severe_events=[dict(round=e['round'],client=c['client'],**c['native_head']) for e in run.get('evaluations',[]) for c in e['clients'] if c['native_head']['occupied']==1 or c['native_head']['largest']>=.99],
                 training_seconds=sum(r['seconds'] for r in run.get('rows',[])), traffic=run.get('traffic'),
                 relation_comparisons=run.get('relation_comparisons'),mismatches=run.get('mismatches'),
                 final_native_quality={k: float(np.mean([m[k] for m in native if k in m])) if any(k in m for m in native) else None for k in ('acc', 'nmi', 'ari', 'largest', 'empty')})
        summary_runs.append(s)
        report_lines += [f'## {label}', '',
                         f"- Setup seconds: {s['setup'].get('seconds') if s['setup'] else None}; feature extraction seconds: {s['setup'].get('feature_extraction_seconds') if s['setup'] else None}; conversion seconds: {s['setup'].get('conversion_seconds') if s['setup'] else None}.",
                         f"- Probe seconds total: {s['probe_seconds']}.",
                         f"- Final native-head mean ACC/NMI/ARI: {s['final_native_quality']['acc']} / {s['final_native_quality']['nmi']} / {s['final_native_quality']['ari']}.",
                         f"- Full-trajectory single-cluster or max-cluster >=99% events: {len(max_events)}.",
                         '- Last 50 T2 private-probe summaries by client:']
        for item in per_client:
            report_lines.append(f"  - Client {item['client']}: max-cluster mean={item['last50_private_max_cluster_mean']}, empty-cluster mean={item['last50_private_empty_clusters_mean']}, entropy mean={item['last50_private_entropy_mean']}.")
        report_lines.append('Final native-head results by client:')
        for event in native_rows:
            for c in event['clients']:report_lines.append(f"- Client {c['client']}: {c['native_head']}")
        report_lines.append('')
    boundary=[]
    for run in runs:
        end=run['case']['until']
        for event in run['diagnostics']:
            if event['stage']!='T2' or event['round'] not in (end,end+1,end+10,run['config']['rounds']):continue
            for c in event['clients']:
                boundary.append(dict(partition=run['case']['partition'],setting=run['case']['setting'],
                    until=end,strength=run['case']['strength'],round=event['round'],client=c['client'],
                    private_largest=c['private']['largest'],private_fit=c['private']['privatepseudo_fit'],
                    private_empty=c['private']['empty'],public_largest=c['public']['largest'],
                    min_pseudo_recall=min(v for v in c['private']['pseudo_recall'] if v is not None),
                    teacher_positive_rate=event['teacher_positive_rates'][c['client']]))
    _write_csv(out/'shutdown_checkpoints.csv',boundary)
    costs=[]
    for run in runs:
        costs.append(dict(partition=run['case']['partition'],setting=run['case']['setting'],
            training_seconds=sum(r['seconds'] for r in run['rows']),
            guard_seconds=sum(c['seconds'] for r in run['rows'] for c in r['stats']['guard_clients']),
            active_rounds=sum(r['stats']['guard_active'] for r in run['rows']),
            violations=sum(c['violations'] for r in run['rows'] for c in r['stats']['guard_clients']),
            upstream_bytes=run['traffic'].get('upstream_bytes'),traffic=run['traffic']))
    _write_csv(out/'guard_costs.csv',costs)
    report_lines += ['## Interpretation', '',
        'Exploratory one-seed study. Compare baseline, duration and strength within each partition.',
        'No automatic winner is declared. Check ALL clients and post-shutdown rebound, not only the 99% threshold.',
        'Probe/oracle/evaluation time is excluded; actual guard computation IS included in training.',
        'Repeated private/public/stage events are observations, not independent trials.',
        'All methods here use direct relation certification; this experiment does not estimate D/B speedup.',
        'See shutdown_checkpoints.csv, guard_costs.csv and test_quality.csv.']
    (out / 'summary.json').write_text(json.dumps(dict(runs=summary_runs), indent=2, ensure_ascii=False), encoding='utf-8')
    (out / 'report.md').write_text('\n'.join(report_lines), encoding='utf-8')
    return dict(runs=len(runs), diagnostics=len(diagnostics), test_quality=len(quality))
