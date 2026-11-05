"""Auditable timing, quality, communication, and memory summaries."""
import csv
import json
import statistics as st
from pathlib import Path


def _write(path, rows):
    if rows:
        with path.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def _unpack(meta, record):
    method = meta['method']
    s = record['summary'][method]
    final = s['final_metrics']['mean']
    head = s['head_pipeline_seconds']
    prep = record['common_preparation_seconds']
    loading = record['shared_loading_seconds']
    rr = [x for x in record['round_records'] if x['method'] == method]
    n = meta['clients']
    return dict(**meta, head_seconds=head, head_seconds_per_client_serial_average=head / n,
        generation_seconds=s['generation_seconds'], private_seconds=s['private_seconds'],
        exchange_seconds=s['exchange_seconds'], public_seconds=s['public_seconds'],
        generation_fraction=s['generation_fraction'], teacher_recompute_fraction=s['teacher_recompute_fraction'],
        teacher_forward_endpoints=sum(x['teacher_forward_endpoints'] for x in rr),
        certified_edges_after_initialization=sum(x['certified_edges_before_refresh'] for x in rr[1:]),
        common_preparation_seconds=prep, shared_loading_seconds=loading,
        head_with_shared_preparation_loading_seconds=prep + loading + head,
        persistent_method_array_bytes=s['persistent_method_array_bytes'],
        raw_communication_bytes=s['traffic']['total_bytes'],
        private_optimizer_steps=sum(x['private_optimizer_steps'] for x in rr),
        public_optimizer_steps=sum(x['public_optimizer_steps'] for x in rr),
        final_acc=final['acc'], final_nmi=final['nmi'], final_ari=final['ari'],
        process_peak_bytes=record['process_peak_bytes'])


def reports(out, runs, memory_runs, fixture=False):
    out = Path(out)
    rows = [_unpack(meta, record) for meta, record in runs]
    pairs = []
    groups = {}
    for row in rows:
        groups.setdefault((row['regime'], row['clients'], row['partition'], row['seed']), {})[row['method']] = row
    for (regime, n, part, seed), methods in sorted(groups.items()):
        if set(methods) != {'B', 'E', 'D'}:
            raise ValueError('Incomplete report triple')
        for ref in ('B', 'E'):
            d, b = methods['D'], methods[ref]
            pairs.append(dict(regime=regime, clients=n, partition=part, seed=seed, comparison='D/' + ref,
                head_ratio=d['head_seconds'] / b['head_seconds'],
                head_saved_seconds=b['head_seconds'] - d['head_seconds'],
                generation_ratio=d['generation_seconds'] / b['generation_seconds'] if b['generation_seconds'] else None,
                generation_saved_seconds=b['generation_seconds'] - d['generation_seconds'],
                with_prep_loading_ratio=d['head_with_shared_preparation_loading_seconds'] / b['head_with_shared_preparation_loading_seconds'],
                with_prep_loading_saved_seconds=b['head_with_shared_preparation_loading_seconds'] - d['head_with_shared_preparation_loading_seconds']))
    summary = []
    keys = sorted({(p['regime'], p['clients'], p['partition'], p['comparison']) for p in pairs})
    for key in keys:
        g = [p for p in pairs if (p['regime'], p['clients'], p['partition'], p['comparison']) == key]
        ratios = [p['head_ratio'] for p in g]
        summary.append(dict(regime=key[0], clients=key[1], partition=key[2], comparison=key[3],
            n_seeds=len(g), median_head_ratio=st.median(ratios), min_head_ratio=min(ratios),
            max_head_ratio=max(ratios), wins=sum(x < 1 for x in ratios),
            median_head_saved_seconds=st.median(p['head_saved_seconds'] for p in g),
            median_generation_ratio=st.median(p['generation_ratio'] for p in g),
            median_with_prep_loading_ratio=st.median(p['with_prep_loading_ratio'] for p in g),
            min_generation_ratio=min(p['generation_ratio'] for p in g),
            max_generation_ratio=max(p['generation_ratio'] for p in g),
            generation_wins=sum(p['generation_ratio'] < 1 for p in g),
            median_generation_saved_seconds=st.median(p['generation_saved_seconds'] for p in g),
            min_with_prep_loading_ratio=min(p['with_prep_loading_ratio'] for p in g),
            max_with_prep_loading_ratio=max(p['with_prep_loading_ratio'] for p in g),
            with_prep_loading_wins=sum(p['with_prep_loading_ratio'] < 1 for p in g),
            median_with_prep_loading_saved_seconds=st.median(p['with_prep_loading_saved_seconds'] for p in g)))

    client_rows, events = [], []
    for meta, record in runs:
        method = meta['method']
        checkpoints = [x for x in record['metrics'] if x['method'] == method]
        for checkpoint in checkpoints:
            for c in checkpoint['clients']:
                row = dict(**meta, round=checkpoint['round'], client=c['client'], width=c['width'],
                    acc=c['acc'], nmi=c['nmi'], ari=c['ari'], occupied_clusters=c['occupied_clusters'],
                    largest_cluster_fraction=c['largest_cluster_fraction'])
                client_rows.append(row)
                events.append(dict(**meta, round=checkpoint['round'], client=c['client'],
                    single_cluster=(c['occupied_clusters'] == 1),
                    largest_cluster_at_least_099=(c['largest_cluster_fraction'] >= .99),
                    occupied_clusters=c['occupied_clusters'], largest_cluster_fraction=c['largest_cluster_fraction']))

    memory = []
    for meta, record in memory_runs:
        method = meta['method']
        memory.append(dict(**meta, process_peak_bytes=record['process_peak_bytes'],
            persistent_method_array_bytes=record['summary'][method]['persistent_method_array_bytes'],
            scope='isolated process; no oracle; endpoint only'))

    _write(out / 'runs.csv', rows); _write(out / 'paired_cost.csv', pairs)
    _write(out / 'paired_summary.csv', summary)
    _write(out / 'client_checkpoints.csv', client_rows)
    _write(out / 'collapse_checkpoints.csv', events)
    _write(out / 'memory.csv', memory)
    final_rounds = {}
    for e in events:
        key = (e['regime'], e['clients'], e['partition'], e['seed'], e['method'])
        final_rounds[key] = max(final_rounds.get(key, -1), e['round'])
    _write(out / 'final_clients.csv', [e for e in client_rows if e['round'] == final_rounds[
        (e['regime'], e['clients'], e['partition'], e['seed'], e['method'])]])
    flagged = [e for e in events if e['single_cluster'] or e['largest_cluster_at_least_099']]
    # Always create an event file, including the meaningful zero-event outcome.
    with (out / 'collapse_events.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(events[0]))
        writer.writeheader(); writer.writerows(flagged)
    final_collapse_rows = sum(e['single_cluster'] or e['largest_cluster_at_least_099'] for e in events
        if e['round'] == final_rounds[(e['regime'], e['clients'], e['partition'], e['seed'], e['method'])])
    (out / 'summary.json').write_text(json.dumps(dict(fixture=fixture, summary=summary, runs=len(rows),
        memory_runs=len(memory), final_collapse_rows=final_collapse_rows,
        note='Shared preparation and loading remain included cost references even when reused. Per-client head is serial total divided by N, descriptive only; it is not a parallel delay estimate.'), ensure_ascii=False, indent=2), encoding='utf-8')

    lines = ['# STL-10 client scaling report', '',
        f"{'Synthetic smoke fixture' if fixture else 'Official STL-10'}; {len(rows)} normal runs; {len(memory)} isolated memory runs.", '',
        'Runs are summarized by regime, N, and partition across seeds. Shared preparation and loading are measured cost references and are not zeroed for reuse. Per-client head is total serial head time divided by N; it is descriptive and not an estimate of parallel delay.', '',
        '| Regime | N | Partition | Comparison | Seeds | Median head ratio | Range | Wins | Median head saved (s) | Median gen ratio | Median prep+load+head ratio |', '|---|---:|---|---|---:|---:|---|---:|---:|---:|---:|']
    for s in summary:
        lines.append(f"| {s['regime']} | {s['clients']} | {s['partition']} | {s['comparison']} | {s['n_seeds']} | {s['median_head_ratio']:.4f} | {s['min_head_ratio']:.4f}–{s['max_head_ratio']:.4f} | {s['wins']}/{s['n_seeds']} | {s['median_head_saved_seconds']:.3f} | {s['median_generation_ratio']:.4f} | {s['median_with_prep_loading_ratio']:.4f} |")
    lines += ['', '## Final collapse events', '', 'A final collapse is any client with one occupied cluster or a largest-cluster fraction ≥0.99 at its final checkpoint. This is an automatic descriptive flag and does not require an ACC gain.', '', '| Regime | N | Partition | Seed | Method | Final collapsed clients |', '|---|---:|---|---:|---|---:|']
    for meta, record in runs:
        clients = record['summary'][meta['method']]['final_metrics']['clients']
        count = sum(c['occupied_clusters'] == 1 or c['largest_cluster_fraction'] >= .99 for c in clients)
        lines.append(f"| {meta['regime']} | {meta['clients']} | {meta['partition']} | {meta['seed']} | {meta['method']} | {'**'+str(count)+'**' if count else '0'} |")
    lines += ['', 'Detailed final per-client metrics are in `final_clients.csv`; all checkpoints are in `client_checkpoints.csv` and `collapse_checkpoints.csv`. `collapse_events.csv` contains only flagged client/checkpoint events. Repeated B/E/D observations are the same quality trajectory, not independent quality evidence.',
              '`runs.csv` includes head phases, exchange, endpoint counts, optimization steps, quality, persistent arrays, serialized traffic, and prep/loading costs. `paired_cost.csv` preserves each seed; `paired_summary.csv` also includes generation and prep-inclusive ranges and win counts. Memory runs are limited to endpoint N and one seed; peak includes interpreter and input verification/loading, with oracle and evaluation disabled.',
              'These are exploratory single measurements per method/configuration. Cross-N changes private splits, representations and trajectories. Serial exchange and serialized bytes do not measure network latency or parallel round time. Any flagged severe final collapse limits claims of useful clustering scalability; costs remain disclosed without selective deletion.', '']
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
    return summary
