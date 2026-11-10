"""P3 uses unchanged scaling accounting and adds a single B quality trajectory."""
import csv
import json
from pathlib import Path
from experiments.client_scaling.report import reports as core_reports


def reports(out, runs, memory_runs, fixture=False):
    for meta, record in runs + memory_runs:
        cfg = record['config']
        if cfg['head_lr'] != .1 or cfg['public_weight'] != .5 or meta['regime'] != 'fixed_per_client':
            raise ValueError('P3 report received a different learning protocol')
    summary = core_reports(out, runs, memory_runs, fixture=fixture)
    rows = []
    for meta, record in runs:
        if meta['method'] != 'B':
            continue
        checkpoints = record['metrics']
        final = checkpoints[-1]['clients']
        rows.append(dict(clients=meta['clients'], partition=meta['partition'], seed=meta['seed'],
            final_single_clients=sum(c['occupied_clusters'] == 1 for c in final),
            final_near99_clients=sum(c['largest_cluster_fraction'] >= .99 for c in final),
            final_mean_largest_fraction=sum(c['largest_cluster_fraction'] for c in final)/len(final),
            worst_checkpoint_mean_largest_fraction=max(sum(c['largest_cluster_fraction'] for c in m['clients'])/len(m['clients']) for m in checkpoints),
            any_checkpoint_single_clients=max(sum(c['occupied_clusters'] == 1 for c in m['clients']) for m in checkpoints),
            severe_final_collapse=any(c['occupied_clusters'] == 1 or c['largest_cluster_fraction'] >= .99 for c in final)))
    with (Path(out)/'quality_guardrails.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    scope = dict(public_effective_lr=.05, private_lr=.1, public_steps_per_client=2,
                 private_samples_per_client=32 if fixture else 400,
                 severe_final_cases=sum(r['severe_final_collapse'] for r in rows),
                 quality_trajectories=len(rows), independent_technical_repeats=False,
                 scope='Fixed samples per client; total private data and public workload increase with N. No cross-N causal isolation or parallel-latency claim.')
    (Path(out)/'scope.json').write_text(json.dumps(scope,indent=2),encoding='utf-8')
    path=Path(out)/'report.md'
    text=path.read_text(encoding='utf-8').replace('# STL-10 client scaling report','# P3 STL-10 fixed-per-client scaling at public LR 0.05',1)
    text+='\n## P3 protocol and quality scope\n\nPrivate LR 0.1; public effective LR 0.05; public two steps per client per round. Private samples per client: '+str(scope['private_samples_per_client'])+'. This is a new fixed-per-client experiment, separate from historical fixed-total LR 0.1 results. Cross-N changes data, encoders and trajectories. No ACC improvement requirement.\n\n`quality_guardrails.csv` summarizes the shared B/E/D quality once using B: '+str(scope['severe_final_cases'])+'/'+str(len(rows))+' cases have severe final collapse. Flagged costs remain reported; these cases cannot support a claim of healthy clustering at scale. Intermediate concentration is recorded without automatically rejecting a recovered trajectory. No timing exclusions or success thresholds are selected after results.\n'
    path.write_text(text,encoding='utf-8')
    return summary
