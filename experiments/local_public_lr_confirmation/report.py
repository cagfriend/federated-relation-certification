"""Per-case severe-collapse audit and explicit historical-reference tables."""
import csv
import json
from pathlib import Path
from .design import cases as registered_cases


CHECKPOINTS = (160, 180, 200)


def recovery(record, checkpoints=CHECKPOINTS):
    by_round = {m['round']: m for m in record.get('metrics', [])}
    results = []
    for rnd in checkpoints:
        clients = {c['client']: c for c in by_round.get(rnd, {}).get('clients', [])}
        for client in range(6):
            metric = clients.get(client)
            passed = (metric is not None and metric['occupied_clusters'] > 1
                      and metric['largest_cluster_fraction'] < .99)
            results.append(dict(round=rnd, client=client, present=metric is not None,
                passed=passed, occupied_clusters=None if metric is None else metric['occupied_clusters'],
                largest_cluster_fraction=None if metric is None else metric['largest_cluster_fraction'],
                nmi=None if metric is None else metric['nmi']))
    return dict(passed=all(x['passed'] for x in results), details=results,
                client_passed={str(c): all(x['passed'] for x in results if x['client'] == c)
                               for c in range(6)})


def _csv(path, rows):
    if not rows:
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def reports(out, completed, references, fixture=False, history=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    checkpoints = (1, 2, 3) if fixture else CHECKPOINTS
    rows, stages, losses, recovery_rows, initial, tests = [], [], [], [], [], []
    expected = {c['case_id'] for c in registered_cases('smoke' if fixture else 'full')}
    supplied = [m['case_id'] for m, _ in completed]
    if len(set(supplied)) != len(supplied) or not set(supplied).issubset(expected):
        raise ValueError('Unexpected or duplicate confirmation case')
    if any(m['branch'] != 'local_lr' for m, _ in completed):
        raise ValueError('Only local_lr belongs in confirmation counts')
    histories = history or {}
    history_tests = []
    for meta, record in completed:
        identity = {key: meta[key] for key in ('case_id', 'seed', 'partition', 'branch')}
        verdict = recovery(record, checkpoints)
        rows.append(dict(**identity, rounds=record['config']['rounds'],
                         severe_collapse_released=verdict['passed'],
                         probe_seconds=record['summary']['B']['probe_seconds'],
                         evaluation_seconds=record['validation']['evaluation_seconds_excluded']))
        for item in verdict['details']:
            recovery_rows.append(dict(**identity, **item))
        for client in record['initial_diagnostics']['clients']:
            initial.append(dict(**identity, client=client['client'],
                capacity=client['private_capacity'],
                public_weight=client['actual_public_weight'],
                effective_public_lr=client['actual_public_effective_lr'],
                pseudo_histogram=json.dumps(client['fixed_pseudo_histogram']),
                private_prediction=json.dumps(client.get('private_prediction')),
                public_prediction=json.dumps(client.get('public_probe_prediction'))))
        for diagnostic in record['diagnostic_records']:
            for client in diagnostic['clients']:
                base = dict(**identity, round=diagnostic['round'], client=client['client'],
                            actual_public_weight=client['actual_public_weight'],
                            actual_public_effective_lr=client['actual_public_effective_lr'],
                            private_update_loss=client['private_update_loss'],
                            public_update_loss=client['public_update_loss'],
                            positive_relation_fraction_T1=client['positive_relation_fraction_T1'],
                            teacher_relation_sha256_T1=client['teacher_relation_sha256_T1'],
                            private_order_sha256=json.dumps(client['private_order_sha256']),
                            public_order_sha256=client['public_order_sha256'])
                delta_private = client['T1']['private_update_delta']
                delta_public = client['T2']['public_update_delta']
                for key, value in delta_private.items():
                    base['private_' + key] = value
                for key, value in delta_public.items():
                    base['public_' + key] = value
                losses.append(base)
                for stage in ('T0', 'T1', 'T2'):
                    for domain in ('private', 'public'):
                        summary = client[stage][domain]
                        stages.append(dict(**identity, round=diagnostic['round'],
                            client=client['client'], stage=stage, domain=domain,
                            counts=json.dumps(summary['counts']),
                            occupied_clusters=summary['occupied_clusters'],
                            largest_cluster_fraction=summary['largest_cluster_fraction'],
                            sample_count=summary['sample_count'],
                            fixed_pseudo_fit=summary.get('fixed_pseudo_fit')))
        for metric in record['metrics']:
            for client in metric['clients']:
                tests.append(dict(**identity, round=metric['round'], **client))

    # History is tabulated from fields physically present in source records.
    # Missing late checkpoints remain absent and thus visible as NA on the report.
    for case_id, reference in references.items():
        for metric in reference.get('metrics', []):
            for client in metric.get('clients', []):
                history_tests.append(dict(case_id=case_id, source='quantity_200_round_B',
                                          round=metric['round'], **client))
    for (case_id, branch), reference in histories.get('low_capacity', {}).items():
        for metric in reference.get('metrics', []):
            for client in metric.get('clients', []):
                history_tests.append(dict(case_id=case_id, source=f'low_capacity_{branch}',
                                          round=metric['round'], **client))
    for branch, reference in histories.get('prior_local', {}).items():
        for metric in reference.get('metrics', []):
            for client in metric.get('clients', []):
                history_tests.append(dict(case_id='strong_iid_seed1001',
                    source=f'prior_single_case_{branch}_exploratory', round=metric['round'], **client))

    expected_ids = {case['case_id'] for case in registered_cases('smoke' if fixture else 'full')}
    observed_ids = [row['case_id'] for row in rows]
    all_cases_released = (len(observed_ids) == len(expected_ids)
                          and set(observed_ids) == expected_ids
                          and all(row['severe_collapse_released'] for row in rows))

    severe_events = [row for row in stages if row['occupied_clusters'] == 1
                     or row['largest_cluster_fraction'] >= .99]

    # Explicitly represent unavailable historical late fields as NA rows.
    late_comparison = []
    stage_availability = []
    source_records = []
    for meta, record in completed:
        source_records.append((meta['case_id'], meta['branch'], 'new_local_lr', record))
    for case_id, record in references.items():
        source_records.append((case_id, 'baseline', 'quantity_200_round_B', record))
    for (case_id, branch), record in histories.get('low_capacity', {}).items():
        source_records.append((case_id, branch, f'low_capacity_{branch}', record))
    for branch, record in histories.get('prior_local', {}).items():
        source_records.append(('strong_iid_seed1001', branch,
                               f'prior_single_case_{branch}_exploratory', record))
    for case_id, branch, source_name, record in source_records:
        checkpoint_metrics = {m['round']: m for m in record.get('metrics', [])}
        diagnostics = {d['round']: d for d in record.get('diagnostic_records', [])}
        for rnd in CHECKPOINTS:
            metric = checkpoint_metrics.get(rnd)
            for client in range(6):
                current = None if metric is None else next((c for c in metric['clients'] if c['client'] == client), None)
                late_comparison.append(dict(case_id=case_id, branch=branch, source=source_name,
                    round=rnd, client=client, present=current is not None,
                    occupied_clusters=None if current is None else current['occupied_clusters'],
                    largest_cluster_fraction=None if current is None else current['largest_cluster_fraction'],
                    nmi=None if current is None else current['nmi']))
            round_diag = diagnostics.get(rnd)
            for stage in ('T0', 'T1', 'T2'):
                stage_available = (round_diag is not None and {c['client'] for c in round_diag['clients']} == set(range(6)) and all(stage in c for c in round_diag['clients']))
                stage_availability.append(dict(case_id=case_id, branch=branch, source=source_name,
                    round=rnd, stage=stage, available=stage_available,
                    value='available' if stage_available else 'NA'))

    for name, values in (('runs.csv', rows), ('recovery.csv', recovery_rows),
                         ('initial.csv', initial), ('stages.csv', stages),
                         ('losses_and_deltas.csv', losses), ('test_checkpoints.csv', tests),
                         ('severe_events.csv', severe_events),
                         ('test_severe_events.csv', [r for r in tests if r['occupied_clusters'] == 1 or r['largest_cluster_fraction'] >= .99]),
                         ('historical_test_metrics.csv', history_tests),
                         ('late_comparison.csv', late_comparison),
                         ('historical_stage_availability.csv', stage_availability)):
        _csv(out / name, values)
    document = dict(fixture=fixture, cases=rows, checkpoints=checkpoints,
        expected_case_ids=sorted(expected_ids), all_cases_released=all_cases_released,
        released_case_count=sum(row['severe_collapse_released'] for row in rows),
        counts=dict(new_local_lr_runs=len(completed), new_baseline_runs=0),
        claim_boundary='Severe-collapse release check only; no ACC improvement or certification speed claim.')
    (out / 'summary.json').write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding='utf-8')
    lines = ['# Local public-LR confirmation', '',
        'Synthetic fixture smoke only.' if fixture else 'Three pre-registered local-LR confirmation cases.', '',
        '| Case | Seed | Partition | Checkpoints passing / 18 | Result |',
        '|---|---:|---|---:|---|']
    lines[4:4] = [f"Registered cases released: {document['released_case_count']}/{len(expected_ids)}. An absent case remains in the denominator and prevents an all-cases pass.", '']
    for row in rows:
        count = sum(x['passed'] for x in recovery_rows if x['case_id'] == row['case_id'])
        lines.append(f"| {row['case_id']} | {row['seed']} | {row['partition']} | {count}/18 | {'released severe collapse' if row['severe_collapse_released'] else 'not released'} |")
    lines += ['', 'Only `local_lr` was newly run: clients 0 and 3 use effective public LR 0.0125, other clients use 0.05. Each run uses B, full private data, and two public optimizer steps per client per round. No new baseline run is included.',
        '', 'The pre-registered release criterion requires all six clients to occupy more than one cluster and have largest-cluster fraction below 0.99 at rounds 160, 180, and 200. Missing checkpoints fail. This is not a general healthy-clustering or accuracy-improvement claim.',
        '', 'Historical quantity B tests and low-capacity baseline/global-low/private-only tests are listed only at their recorded checkpoints. The earlier single-case local-LR result is marked exploratory. Unrecorded late historical fields remain missing; this report does not infer them.',
        '', 'The experiment does not claim certification speedup. Reducing two clients’ public update rate also changes later coupled teacher feedback.', '']
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    return document
