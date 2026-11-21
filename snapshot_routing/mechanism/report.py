"""Report counts from diagnostic replay and times from independent E42 runs."""

from statistics import mean, median

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt

from experiments.snapshot_graph_scaling.design import cell_id

from ..report import eligible, seconds, write_csv
from .replay import STATE_FIELDS


def summarize(case, data, blocks, preset):
    cell = cell_id(case)
    rows = []
    for r in data['rows']:
        for c in r['clients']:
            entry = dict(cell=cell, **case, round=r['round'], client=c['client'], width=c['width'],
                         certificate_active=r['round'] > 1, e_forward=c['e_forward'], d_forward=c['d_forward'])
            for mode in ('e','d'):
                state = c[f'{mode}_state'] or {}
                entry.update({f'{mode}_state_{k}': state.get(k) for k in STATE_FIELDS})
            rows.append(entry)
    steady = [r for r in rows if r['certificate_active']]
    edges = len(steady)*case['public_size']//2
    matched = [g for g in blocks if eligible(g, preset)]
    elapsed = {m: mean(seconds(g[m]) for g in matched) if matched else None for m in 'BED'}
    e = sum(r['e_forward'] for r in rows)
    d = sum(r['d_forward'] for r in rows)
    b = len(rows)*case['public_size']
    stats = dict(cell=cell, **case, checked_edges=data['comparisons'], steady_edge_opportunities=edges,
                 b_forward=b, e_forward=e, d_forward=d, e_minus_d_endpoints=e-d, b_minus_d_endpoints=b-d,
                 d_vs_e_endpoints_saved_pct=100*(1-d/e),
                 d_vs_b_endpoints_saved_pct=100*(1-d/b), e_cache_bytes=data['cache_bytes']['E'],
                 d_cache_bytes=data['cache_bytes']['D'], timing_blocks=len(matched))
    for mode in ('e','d'):
        extra = sum(r[f'{mode}_state_extra_edges'] for r in steady)
        point = sum(r[f'{mode}_state_point_forward'] for r in steady)
        rel = sum(r[f'{mode}_state_relation_forward'] for r in steady)
        stats.update({f'{mode}_state_extra_edges': extra,
                      f'{mode}_state_extra_edge_pct': 100*extra/edges,
                      f'{mode}_state_endpoints_skipped_on_same_candidates': point-rel})
    for m, value in elapsed.items():
        stats[f'e42_{m.lower()}_seconds'] = value
    for baseline in 'BE':
        name = f'e42_d_vs_{baseline.lower()}'
        stats[f'{name}_saved_seconds'] = elapsed[baseline]-elapsed['D'] if matched else None
        stats[f'{name}_saved_pct'] = 100*(1-elapsed['D']/elapsed[baseline]) if matched else None
        stats[f'{name}_wins'] = sum(seconds(g['D']) < seconds(g[baseline]) for g in matched)
    return stats, rows


def quantiles_by_size(summary):
    fields = ('e_state_extra_edge_pct','d_state_extra_edge_pct','d_vs_e_endpoints_saved_pct',
              'd_vs_b_endpoints_saved_pct','e42_d_vs_b_saved_pct','e42_d_vs_e_saved_pct',
              'e42_d_vs_b_saved_seconds','e42_d_vs_e_saved_seconds')
    output = []
    for size in sorted({r['public_size'] for r in summary}):
        subset = [r for r in summary if r['public_size'] == size]
        for key in fields:
            values = [r[key] for r in subset if r[key] is not None]
            output.append(dict(public_size=size, indicator=key, cells=len(values),
                               minimum=min(values) if values else None, median=median(values) if values else None,
                               maximum=max(values) if values else None))
    return output


def figure(out, summary, preset):
    sizes = sorted({r['public_size'] for r in summary})
    blue, green = '#236392', '#8B4F97'
    panels = [
        ('A  Extra certified edges (%)',
         [('e_state_extra_edge_pct', 'E cache', blue), ('d_state_extra_edge_pct', 'D cache', green)]),
        ('B  Endpoints skipped by D (%)',
         [('d_vs_b_endpoints_saved_pct', 'vs B', blue), ('d_vs_e_endpoints_saved_pct', 'vs E', green)]),
        ('C  Net generation time saved by D (%)',
         [('e42_d_vs_b_saved_pct', 'vs B', blue), ('e42_d_vs_e_saved_pct', 'vs E', green)]),
        ('D  Persistent certificate arrays (MiB)',
         [('e_cache_mib', 'E cache', blue), ('d_cache_mib', 'D cache', green)]),
    ]
    sparse = [dict(r, e_cache_mib=r['e_cache_bytes']/2**20, d_cache_mib=r['d_cache_bytes']/2**20)
              for r in summary]
    fig, axes = plt.subplots(2, 2, figsize=(9, 5.8), layout='constrained')
    for ax, (title, measures) in zip(axes.ravel(), panels, strict=True):
        for j, (key, label, color) in enumerate(measures):
            offset = -.13 if j == 0 else .13
            ax.scatter([], [], color=color, marker='D', s=22, label=label)
            for i, size in enumerate(sizes):
                values = [r[key] for r in sparse if r['public_size'] == size and r[key] is not None]
                if not values:
                    continue
                # Deterministic small offsets expose coincident configuration dots.
                dither = [(k-(len(values)-1)/2)*.017 for k in range(len(values))]
                ax.scatter([i+offset+x for x in dither], values, color=color, s=14, alpha=.55)
                ax.scatter(i+offset, median(values), color=color, marker='D', edgecolors='white', s=42, zorder=3)
        ax.set_xticks(range(len(sizes)), [f'{m:,}' for m in sizes])
        ax.set_xlim(-.45, len(sizes)-.55)
        ax.set_xlabel('Public samples (M)')
        ax.set_title(title, loc='left', fontsize=10, weight='bold')
        ax.grid(axis='y', alpha=.22)
        ax.spines[['top','right']].set_visible(False)
        ax.legend(loc='best', frameon=False, fontsize=8)
        if ax is axes[1, 0]:
            ax.axhline(0, color='#777777', lw=.8)
    title = 'Synthetic check' if preset == 'smoke' else 'Incremental cost and coverage of exact relation certification'
    fig.suptitle(title, weight='bold')
    for ext in ('pdf','png'):
        fig.savefig(out/f'mechanism.{ext}', dpi=260)
    plt.close(fig)


def build(out, cases, analyzed, times, preset):
    client_rows, cells = [], []
    for case in cases:
        cell = cell_id(case)
        summary, rows = summarize(case, analyzed[cell], times[cell], preset)
        cells.append(summary)
        client_rows.extend(rows)
    sizes = quantiles_by_size(cells)
    write_csv(out/'client_round.csv', client_rows)
    write_csv(out/'cell_summary.csv', cells)
    write_csv(out/'size_summary.csv', sizes)
    figure(out, cells, preset)
    lines = ['# D 相对 E 的关系认证机制', '',
             f"共 {len(cells)} 个配置。E/D 回放与全量 B 完成 "
             f'{sum(c["checked_edges"] for c in cells):,} 次关系核对，全部一致。'
             '逐轮重算端点数及缓存大小均与封存的 E42 独立计时记录相同。', '',
             '| 公共规模 | E 缓存额外判边中位数 | D 缓存额外判边中位数 | D 对 E 少重算端点中位数 |'
             ' E42 D 对 E 净省时中位数 | E42 D 对 B 净省时中位数 |',
             '|---:|---:|---:|---:|---:|---:|']
    values = {(a['public_size'],a['indicator']): a['median'] for a in sizes}
    for m in sorted({r['public_size'] for r in cells}):
        keys = ('e_state_extra_edge_pct','d_state_extra_edge_pct','d_vs_e_endpoints_saved_pct',
                'e42_d_vs_e_saved_pct','e42_d_vs_b_saved_pct')
        entries = [values[m,key] for key in keys]
        lines.append(f'| {m} | ' + ' | '.join('NA' if x is None else f'{x:+.2f}%' for x in entries) + ' |')
    lines += ['', '额外判边在同一组候选集合内计数，分 E 缓存和 D 缓存，首轮排除。'
               '少重算量来自 E/D 各自持续演化的缓存，含首轮。每个图点是一项种子与划分配置，菱形是该档中位数。'
               '耗时引用 E42 有效配对，含首次缓存初始化。诊断回放记录计数。']
    if preset == 'smoke':
        lines += ['', '合成短测仅核验流程。']
    (out/'report.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
