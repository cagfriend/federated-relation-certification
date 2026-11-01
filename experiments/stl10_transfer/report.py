"""Descriptive paired summaries for the preregistered STL-10 transfer run."""
import csv,json,statistics as st
from pathlib import Path
from .design import METHODS

def _csv(path,rows):
 if rows:
  with Path(path).open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def aggregate(runs):
 rows=[]
 for r in runs:
  s=r['summary'][r['method']]; fm=s['final_metrics']
  rows.append(dict(seed=r['seed'],partition=r['partition'],case_id=r['case_id'],method=r['method'],dataset=r['dataset'],
   head_pipeline_seconds=s['head_pipeline_seconds'],generation_seconds=s['generation_seconds'],
   with_shared_preparation_seconds=s['with_shared_preparation_seconds'],
   generation_fraction=s.get('generation_fraction'),teacher_recompute_fraction=s.get('teacher_recompute_fraction'),traffic_total_bytes=s.get('traffic',{}).get('total_bytes'),
   process_peak_bytes=r.get('process_peak_bytes'),persistent_method_array_bytes=s['persistent_method_array_bytes'],
   final_acc=fm['mean']['acc'],final_nmi=fm['mean']['nmi'],final_ari=fm['mean']['ari']))
 groups={}
 for x in rows:groups.setdefault((x['partition'],x['case_id']),{}).setdefault(x['seed'],{})[x['method']]=x
 paired=[]
 for (part,cid),seeds in sorted(groups.items()):
  for seed,ms in sorted(seeds.items()):
   if not all(m in ms for m in METHODS):continue
   for other in ('B','E'):
    d,b=ms['D'],ms[other]
    paired.append(dict(partition=part,case_id=cid,seed=seed,comparison=f'D/{other}',
     head_ratio=d['head_pipeline_seconds']/b['head_pipeline_seconds'],saved_seconds=b['head_pipeline_seconds']-d['head_pipeline_seconds'],
     generation_ratio=(d['generation_seconds']/b['generation_seconds'] if b['generation_seconds'] else None),D_acc=d['final_acc'],reference_acc=b['final_acc']))
    paired[-1].update(with_preparation_ratio=d['with_shared_preparation_seconds']/b['with_shared_preparation_seconds'],with_preparation_saved_seconds=b['with_shared_preparation_seconds']-d['with_shared_preparation_seconds'])
 summary=[]
 for key in sorted({(x['partition'],x['case_id'],x['comparison']) for x in paired}):
  g=[x for x in paired if (x['partition'],x['case_id'],x['comparison'])==key]; v=[x['head_ratio'] for x in g]
  summary.append(dict(partition=key[0],case_id=key[1],comparison=key[2],n_seeds=len(g),median_head_ratio=st.median(v),min_head_ratio=min(v),max_head_ratio=max(v),head_wins=sum(z<1 for z in v),median_saved_seconds=st.median(x['saved_seconds'] for x in g)))
  summary[-1].update(median_with_preparation_ratio=st.median(x['with_preparation_ratio'] for x in g),median_with_preparation_saved_seconds=st.median(x['with_preparation_saved_seconds'] for x in g))
 quality=[]
 by={ (r['partition'],r['seed'],r['case_id']):r for r in runs }
 cases=sorted({(r['spec']['config']['samples'],r['case_id']) for r in runs})
 if len(cases)==2:
  (mlo,lo),(mhi,hi)=cases
  finals={(r['partition'],r['seed'],r['case_id']):r for r in runs if r['method']=='D'}
  for part in sorted({r['partition'] for r in runs}):
   for seed in sorted({r['seed'] for r in runs}):
    a=finals.get((part,seed,lo));b=finals.get((part,seed,hi))
    if a and b:
     x=a['summary']['D']['final_metrics']['mean']['acc'];y=b['summary']['D']['final_metrics']['mean']['acc']
     quality.append(dict(partition=part,seed=seed,M_low=mlo,M_high=mhi,acc_low=x,acc_high=y,change_high_minus_low=y-x,within_1pp=y-x>=-0.01-1e-12))
 return rows,paired,summary,quality
def reports(output,runs,fixture,preset):
 output=Path(output);rows,paired,summary,quality=aggregate(runs)
 _csv(output/'runs.csv',rows);_csv(output/'paired_cost.csv',paired);_csv(output/'paired_summary.csv',summary);_csv(output/'cross_M_ACC_sensitivity.csv',quality)
 (output/'summary.json').write_text(json.dumps(dict(paired_summary=summary,cross_M_ACC_sensitivity=quality,completed_runs=len(runs),dataset='STL-10 fixture' if fixture else 'STL-10',formal_independent_confirmation=False),indent=2),encoding='utf-8')
 lines=['# STL-10 transfer experiment report','',f"Dataset: **{'synthetic STL-10 fixture (smoke only)' if fixture else 'official STL-10'}**. Runs: {len(runs)}; preset: {preset}.",'',
 'Each method was run once per seed, partition and M in an independent serial process. Results are exploratory; this is not a formal independent confirmation and no C1/C2 verdict is made. Paired seed results are summarized by median and range, with win counts.','',
 '## Paired timing','', '| partition | case | comparison | seeds | median head ratio | range | wins | median seconds saved |','|---|---|---:|---:|---:|---:|---:|---:|']
 for x in summary:lines.append(f"| {x['partition']} | {x['case_id']} | {x['comparison']} | {x['n_seeds']} | {x['median_head_ratio']:.4f} | {x['min_head_ratio']:.4f}–{x['max_head_ratio']:.4f} | {x['head_wins']}/{x['n_seeds']} | {x['median_saved_seconds']:.3f} |")
 lines += ['', '## Including shared preparation and loading', '', '| partition | case | comparison | median cost ratio | median seconds saved |', '|---|---|---|---:|---:|']
 for x in summary:lines.append(f"| {x['partition']} | {x['case_id']} | {x['comparison']} | {x['median_with_preparation_ratio']:.4f} | {x['median_with_preparation_saved_seconds']:.3f} |")
 lines += ['', '## Cross-M quality sensitivity','', 'M changes the public graph and target. This comparison is a sensitivity analysis, not a D-specific budget loss. The registered 1 percentage point ACC tolerance is reported per seed; private data, pseudo-labels, initial heads, and public SGD step budget are held fixed across M, while graph targets may differ.','', '| partition | seed | ACC change, larger M minus smaller M | within −1 pp |','|---|---:|---:|---|']
 for x in quality:lines.append(f"| {x['partition']} | {x['seed']} | {x['change_high_minus_low']:+.4f} | {'yes' if x['within_1pp'] else 'no'} |")
 lines += ['', '## Per-run diagnostics','', 'Full per-client ACC/NMI/ARI and cluster occupancy are retained in each run JSON under `metrics`; persistent traffic arrays and peak-memory descriptions are retained under each method summary. The C0 preparation and load costs are included in `with_shared_preparation_seconds`; maximum-pool preparation is shared and its original preparation cost is charged to either M. Audit/evaluation time is excluded from the head timer.','']
 (output/'report.md').write_text('\n'.join(lines),encoding='utf-8');return summary
