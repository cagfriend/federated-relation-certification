"""Export quality and observer-only cost curves from completed pilot runs."""
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

METHODS = ('Ours', 'Hetero-SSFL', 'FLESD', 'FedMKD')
QUALITY = ('acc', 'nmi', 'ari', 'occupied', 'empty', 'largest')


def _csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def _num(x, default=0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def export(out, cfg=None):
    out = Path(out)
    quality_rows, cost_rows, curve_rows = [], [], []
    for path in sorted((out / 'runs').glob('*.json')):
        result = json.loads(path.read_text(encoding='utf-8'))
        case, partition, method = result['case'], result['case']['partition'], result['case']['method']
        setup = _num(result.get('setup_seconds'))
        profile_path = out / 'profiles' / f'{partition}_{method}.json'
        profile = json.loads(profile_path.read_text(encoding='utf-8')) if profile_path.exists() else {}
        rows = result.get('rows', [])
        setup_cost = profile.get('setup') or {}
        setup_timing = (result.get('setup_details') or {}).get('timing') or {}
        setup_traffic = result.get('setup_traffic') or {}
        setup_total, setup_up, setup_down = (_num(setup_traffic.get(k)) for k in ('total_bytes', 'up_bytes', 'down_bytes'))
        cost_rows.append(dict(partition=partition, method=method, round=0, seconds=setup,
            computation_seconds=setup_timing.get('compute_seconds', ''),
            serialization_seconds=setup_timing.get('serialization_seconds', ''),
            aggregation_seconds=setup_timing.get('aggregation_seconds', ''), other_seconds='',
            cumulative_method_seconds=setup, cumulative_bytes=setup_total,
            delta_up_bytes=setup_up, delta_down_bytes=setup_down, delta_total_bytes=setup_total,
            cumulative_up_bytes=setup_up, cumulative_down_bytes=setup_down,
            cumulative_total_bytes=setup_total,
            feature_extraction_seconds=(result.get('setup_details') or {}).get('feature_extraction_seconds', ''),
            common_ae_seconds=(result.get('setup_details') or {}).get('common_ae_seconds', result.get('common_ae_seconds', '')),
            dense_macs=setup_cost.get('macs', ''), dense_flops=setup_cost.get('flops', ''),
            coverage=profile.get('coverage', ''), trajectory_verified=profile.get('trajectory_verified', ''),
            measured_sha256=profile.get('measured_sha256', ''),
            traffic_delta_bytes=setup_total,
            setup_details=json.dumps(result.get('setup_details', {}), ensure_ascii=False, sort_keys=True)))
        # Legacy runs have cumulative traffic in traffic; new runs may include
        # an explicit per-round traffic_delta.
        elapsed, byte_fallback = setup, setup_total
        up_fallback, down_fallback = setup_up, setup_down
        points = {0: (setup, setup_total, setup_up, setup_down)}
        profile_rounds = profile.get('rounds', [])
        for index, row in enumerate(rows):
            t = row.get('timing') or {}
            costs = profile_rounds[index] if index < len(profile_rounds) else {}
            dt = _num(row.get('seconds'), sum(_num(t.get(k)) for k in ('compute_seconds', 'serialization_seconds', 'aggregation_seconds', 'other_seconds')))
            if not dt:
                dt = _num(row.get('seconds'))
            elapsed += dt
            delta = row.get('traffic_delta')
            if isinstance(delta, dict):
                byte_fallback += _num(delta.get('total_bytes', delta.get('bytes')))
                up_fallback += _num(delta.get('up_bytes'))
                down_fallback += _num(delta.get('down_bytes'))
            else:
                tr = row.get('traffic') or {}
                byte_fallback = _num(tr.get('total_bytes', tr.get('bytes')), byte_fallback)
                up_fallback = _num(tr.get('up_bytes'), up_fallback)
                down_fallback = _num(tr.get('down_bytes'), down_fallback)
            points[int(row.get('round', len(points)))] = (elapsed, byte_fallback, up_fallback, down_fallback)
            comp = dict(costs)
            comp.setdefault('dense_macs', comp.get('macs', ''))
            comp.setdefault('dense_flops', comp.get('flops', ''))
            cost_rows.append(dict(partition=partition, method=method, round=row.get('round'),
                seconds=row.get('seconds', ''), computation_seconds=t.get('compute_seconds', ''),
                serialization_seconds=t.get('serialization_seconds', ''), aggregation_seconds=t.get('aggregation_seconds', ''),
                other_seconds=t.get('other_seconds', ''), cumulative_method_seconds=elapsed,
                cumulative_bytes=byte_fallback, delta_up_bytes=_num((row.get('traffic_delta') or {}).get('up_bytes')),
                delta_down_bytes=_num((row.get('traffic_delta') or {}).get('down_bytes')),
                delta_total_bytes=_num((row.get('traffic_delta') or {}).get('total_bytes')),
                cumulative_up_bytes=up_fallback, cumulative_down_bytes=down_fallback,
                cumulative_total_bytes=byte_fallback,
                feature_extraction_seconds=(result.get('setup_details') or {}).get('feature_extraction_seconds', ''),
                common_ae_seconds=(result.get('setup_details') or {}).get('common_ae_seconds', result.get('common_ae_seconds', '')),
                dense_macs=comp.get('dense_macs', ''), dense_flops=comp.get('dense_flops', ''),
                coverage=comp.get('coverage', profile.get('coverage', '')),
                trajectory_verified=profile.get('trajectory_verified', ''), measured_sha256=profile.get('measured_sha256', ''),
                traffic_delta_bytes=(row.get('traffic_delta') or {}).get('total_bytes', (row.get('traffic_delta') or {}).get('bytes', '')),
                setup_details=json.dumps(result.get('setup_details', {}), ensure_ascii=False, sort_keys=True)))

        for obs in result.get('evaluations', []):
            rnd = int(obs.get('round', 0))
            elapsed_at, bytes_at, up_at, down_at = points.get(rnd, (elapsed, byte_fallback, up_fallback, down_fallback))
            elapsed_at = _num(obs.get('cumulative_method_seconds'), elapsed_at)
            total_at = _num(obs.get('cumulative_total_seconds'), elapsed_at + _num(result.get('common_ae_seconds')))
            bytes_at = _num(obs.get('cumulative_bytes'), bytes_at)
            for client in obs.get('clients', []):
                variants = [('kmeans', client)]
                if 'native_head' in client:
                    variants.append(('native', client['native_head']))
                for estimator, metrics in variants:
                    qrow = dict(partition=partition, method=method, estimator=estimator,
                        round=rnd, client=client.get('client'))
                    qrow.update({k: metrics.get(k, '') for k in QUALITY})
                    qrow['cluster_counts'] = json.dumps(metrics.get('cluster_counts', []))
                    qrow['cluster_proportions'] = json.dumps(metrics.get('cluster_proportions', []))
                    quality_rows.append(qrow)
                    curve_rows.append(dict(partition=partition, method=method, estimator=estimator,
                        round=rnd, client=client.get('client'), cumulative_method_seconds=elapsed_at, cumulative_total_seconds=total_at,
                        cumulative_bytes=bytes_at, **{k: metrics.get(k, '') for k in ('acc', 'nmi')}))
            # Add an aggregate curve point as client=-1 for readable overall trends.
            means = obs.get('mean', {})
            curve_rows.append(dict(partition=partition, method=method, estimator='kmeans_mean', round=rnd,
                cumulative_method_seconds=elapsed_at, cumulative_total_seconds=total_at,
                cumulative_bytes=bytes_at, acc=means.get('acc', ''), nmi=means.get('nmi', '')))
            native_clients = [c['native_head'] for c in obs.get('clients', []) if 'native_head' in c]
            if native_clients:
                curve_rows.append(dict(partition=partition, method=method, estimator='native_mean', round=rnd,
                    cumulative_method_seconds=elapsed_at, cumulative_total_seconds=total_at,
                    cumulative_bytes=bytes_at,
                    acc=sum(_num(c.get('acc')) for c in native_clients) / len(native_clients),
                    nmi=sum(_num(c.get('nmi')) for c in native_clients) / len(native_clients)))
    _csv(out / 'quality.csv', quality_rows, ('partition','method','estimator','round','client',*QUALITY,'cluster_counts','cluster_proportions'))
    _csv(out / 'round_costs.csv', cost_rows, ('partition','method','round','seconds','computation_seconds','serialization_seconds','aggregation_seconds','other_seconds','cumulative_method_seconds','feature_extraction_seconds','common_ae_seconds','delta_up_bytes','delta_down_bytes','delta_total_bytes','cumulative_up_bytes','cumulative_down_bytes','cumulative_total_bytes','cumulative_bytes','dense_macs','dense_flops','coverage','trajectory_verified','measured_sha256','traffic_delta_bytes','setup_details'))
    _csv(out / 'curves.csv', curve_rows, ('partition','method','estimator','round','client','cumulative_method_seconds','cumulative_total_seconds','cumulative_bytes','acc','nmi'))
    _plots(out, curve_rows)


def _plots(out, rows):
    for partition in sorted({r['partition'] for r in rows}):
        for metric in ('acc', 'nmi'):
            for xfield, xlabel, suffix in (
                ('round', 'Round', 'round'),
                ('cumulative_method_seconds', 'Cumulative method seconds (setup included; evaluation excluded)', 'seconds'),
                ('cumulative_bytes', 'Cumulative communication bytes', 'bytes')):
                fig, ax = plt.subplots(figsize=(8, 5))
                for method in METHODS:
                    for estimator in ('kmeans_mean', 'native_mean'):
                        pts = [r for r in rows if r['partition'] == partition and r['method'] == method and r['estimator'] == estimator and r.get(metric) not in ('', None)]
                        if not pts:
                            continue
                        pts.sort(key=lambda p: float(p[xfield]))
                        is_native = estimator == 'native_mean'
                        label = method + (' native' if is_native else ' KMeans')
                        ax.plot([_num(p[xfield]) for p in pts], [_num(p[metric]) for p in pts],
                                linestyle='--' if is_native else '-', alpha=1,
                                linewidth=2, label=label)
                ax.set(title=f'{partition}: {metric.upper()} vs {suffix}', xlabel=xlabel, ylabel=metric.upper())
                ax.grid(True, alpha=.25)
                handles, labels = ax.get_legend_handles_labels()
                if handles:
                    ax.legend()
                fig.tight_layout()
                fig.savefig(out / f'curve_{partition}_{metric}_{suffix}.png', dpi=150)
                plt.close(fig)
