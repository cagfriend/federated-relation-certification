"""Quantity profiles keep the original paired cost accounting separated by regime."""
from pathlib import Path
import csv,json
from experiments.client_scaling.report import reports as core_reports
from .design import capacities


def reports(out,runs,memory_runs,fixture=False):
    preset='smoke' if fixture else 'full'
    for meta,r in runs+memory_runs:
        wanted=list(capacities(preset,meta['profile']))
        if r['config']['public_weight']!=.5 or r['config']['head_lr']!=.1 or r['round_records'][0]['private_samples_per_client']!=wanted:
            raise ValueError('Quantity report budget/dose mismatch')
        if meta['regime']!='quantity_'+meta['profile']:
            raise ValueError('Profiles must remain separate report regimes')
    summary=core_reports(out,runs,memory_runs,fixture=fixture)
    quality=[];capacity_rows=[]
    for meta,r in runs:
        if meta['method']!='B':continue
        sizes=list(capacities(preset,meta['profile']))
        final=r['metrics'][-1]['clients']
        quality.append(dict(profile=meta['profile'],seed=meta['seed'],partition=meta['partition'],
            final_single_clients=sum(x['occupied_clusters']==1 for x in final),
            final_near99_clients=sum(x['largest_cluster_fraction']>=.99 for x in final),
            final_mean_largest_fraction=sum(x['largest_cluster_fraction'] for x in final)/len(final),
            severe_final_collapse=any(x['occupied_clusters']==1 or x['largest_cluster_fraction']>=.99 for x in final),
            worst_checkpoint_mean_largest_fraction=max(sum(x['largest_cluster_fraction'] for x in m['clients'])/len(m['clients']) for m in r['metrics'])))
        for c,(size,width) in enumerate(zip(sizes,r['config']['dimensions'])):
            capacity_rows.append(dict(profile=meta['profile'],seed=meta['seed'],partition=meta['partition'],client=c,width=width,private_samples=size,
                private_steps_per_round=(size+r['config']['private_batch']-1)//r['config']['private_batch']*r['config']['private_epochs'],
                final_acc=final[c]['acc'],final_nmi=final[c]['nmi'],final_ari=final[c]['ari'],
                final_occupied_clusters=final[c]['occupied_clusters'],final_largest_cluster_fraction=final[c]['largest_cluster_fraction']))
    out=Path(out)
    for name,rows in [('quality_guardrails.csv',quality),('private_capacities.csv',capacity_rows)]:
        with (out/name).open('w',encoding='utf-8',newline='') as handle:
            w=csv.DictWriter(handle,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    scope=dict(fixture=fixture,profiles={p:list(capacities(preset,p)) for p in ('equal','moderate','strong')},
               clients=6,private_total=192 if fixture else 2400,public_effective_lr=.05,
               quality_trajectories=len(quality),severe_final_cases=sum(x['severe_final_collapse'] for x in quality),
               note='Only within-profile method pairs identify certification savings. Across profiles, encoders, pseudo-labels, class allocation and private batch counts may change. Equal aggregation remains unchanged.')
    (out/'scope.json').write_text(json.dumps(scope,indent=2),encoding='utf-8')
    path=out/'report.md';text=path.read_text(encoding='utf-8')
    text=text.replace('# STL-10 client scaling report','# STL-10 private quantity heterogeneity, public LR 0.05',1)
    text+='\n## Quantity profiles\n\nN=6 and total private data are fixed. `quantity_equal`, `quantity_moderate` and `quantity_strong` identify separate regimes; do not pool them into one seed estimate. Widths and global private IDs/public IDs are held fixed, but private partitions and encoders change. Private batching uses actual client sizes, so optimizer-step totals can change across profiles.\n\n`private_capacities.csv` reports actual capacity, width, private steps and per-client final quality once using the shared B trajectory. `quality_guardrails.csv` records severe final collapse without requiring ACC improvement. There are '+str(scope['severe_final_cases'])+'/'+str(len(quality))+' flagged cases; costs remain disclosed for every case. This is a single measurement per method/configuration, not an independent timing confirmation. No extra communication saving is claimed for identical B/E/D trajectories.\n'
    path.write_text(text,encoding='utf-8');return summary
