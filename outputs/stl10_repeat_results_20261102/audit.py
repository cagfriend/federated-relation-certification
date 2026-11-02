import csv
import json
import math
import statistics as st
import tempfile
from pathlib import Path
from experiments.stl10_repeat_confirmation.run import check_environment, check_repeat_run, load_verified_anchors, verify_blocks, check_anchor8
from experiments.stl10_repeat_confirmation.design import plan, schedule, filename
from experiments.stl10_repeat_confirmation.report import reports
from experiments.stl10_transfer.run import digest
from experiments.private_workload.student import selected_edges, schedule_digest

ROOT = Path.cwd()
R = ROOT / 'experiments/stl10_repeat_confirmation/results_full'
OUT = ROOT / 'outputs/stl10_repeat_results_20261102'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def need(ok, msg):
    if not ok: raise ValueError(msg)
def near(a,b): return math.isfinite(a) and math.isclose(a,b,rel_tol=1e-10,abs_tol=1e-9)
env, final = read(R/'environment.json'), read(R/'environment_final.json')
check_environment(env); check_environment(final)
need(all(final[k] == v for k,v in env.items()), 'Environment changed')
need(env['source_hashes'] == read(ROOT/'outputs/stl10_repeat_review_20261102/preflight.json')['current_source_sha256'], 'Approved local source differs')
done, finished = read(R/'completed.json'), read(R/'finished.json')
need(finished['status']=='complete' and finished['expected_runs']==finished['completed_runs']==done['count']==54, 'Completion count differs')
need(digest(R/'completed.json')==finished['completed_manifest_sha256'], 'Completion seal differs')
actual={str(p.relative_to(R)) for p in R.rglob('*') if p.is_file() and p.name not in ('completed.json','finished.json','ARCHIVED_RAW.md')}
need(actual==set(done['files']), 'Manifest coverage differs')
for p,sha in done['files'].items(): need(digest(R/p)==sha,'File digest differs: '+p)
spec=plan('full')[0]; metas=schedule('full')
need({p.name for p in (R/'runs').glob('*.json')}=={filename(m) for m in metas},'Matrix differs')
for entry in env['prepared'].values(): need(digest(Path(entry['path'])/'prepared.json')==entry['metadata_sha256'],'Prepared marker differs')
a8,al,ac=load_verified_anchors(env)
need((len(a8),len(al),len(ac))==(6,4,6),'Historical anchor coverage differs')
completed=[]; details=[]; flags=[]
for meta in metas:
    r=read(R/'runs'/filename(meta)); method=meta['method']; s=r['summary'][method]; rr=r['round_records']
    prep=Path(env['prepared'][f"{meta['seed']}|{meta['partition']}"]['path'])
    check_repeat_run(r,meta,spec,prep,False); check_anchor8(r,a8[meta['seed'],meta['partition']])
    need(r['dataset']=='STL-10','Dataset differs')
    for row in rr:
        need(row['private_samples_per_client']==[834,834,833,833,833,833] and row['private_optimizer_steps']==42 and row['private_forward_endpoints']==5000,'Private work differs')
        need(row['public_optimizer_steps']==12 and row['public_edges_consumed']==3072 and row['student_forward_endpoints']==6144,'Public work differs')
        need(schedule_digest([selected_edges(spec,meta['seed'],c,row['round']) for c in range(6)])==row['public_schedule_digest'],'Student edge order differs')
        need(all(v==row['committed_counts_digest'] for v in row['received_counts_digests']),'Targets differ')
    for phase in ('private','generation','exchange','public'):
        need(near(s[phase+'_seconds'],sum(x[phase+'_seconds'] for x in rr)),'Timing sum differs')
        check=rr[1:] if phase=='generation' else rr
        med=st.median(x[phase+'_seconds'] for x in check)
        for x in check:
            if x[phase+'_seconds']>max(2,10*med): flags.append(dict(**meta,round=x['round'],phase=phase,seconds=x[phase+'_seconds'],median=med))
    need(near(s['head_pipeline_seconds'],s['initialization_seconds']+sum(x['pipeline_seconds'] for x in rr)),'Head timing differs')
    need(near(s['with_shared_preparation_seconds'],r['common_preparation_seconds']+r['shared_loading_seconds']+s['head_pipeline_seconds']),'Preparation total differs')
    need(near(s['teacher_recompute_fraction'],sum(x['teacher_forward_endpoints'] for x in rr[1:])/(199*6*16384)),'Recompute ratio differs')
    need([q['round'] for q in r['metrics']]==list(range(20,201,20)),'Checkpoint grid differs')
    for q in r['metrics']:
        cs=q['clients']; need(len(cs)==6 and [c['client'] for c in cs]==list(range(6)),'Client coverage differs')
        for c in cs:
            counts=c['cluster_counts'];need(len(counts)==10 and sum(counts)==8000 and all(isinstance(v,int) and v>=0 for v in counts),'Invalid cluster counts')
            need(c['occupied_clusters']==sum(v>0 for v in counts) and near(c['largest_cluster_fraction'],max(counts)/8000),'Occupancy differs')
        for k in ('acc','nmi','ari'):need(near(q['mean'][k],st.mean(c[k] for c in cs)),'Mean metric differs')
    completed.append((meta,r))
    details.append(dict(**meta,head_seconds=s['head_pipeline_seconds'],generation_seconds=s['generation_seconds'],private_seconds=s['private_seconds'],public_seconds=s['public_seconds'],with_preparation_seconds=s['with_shared_preparation_seconds'],teacher_recompute_fraction=s['teacher_recompute_fraction'],persistent_bytes=s['persistent_method_array_bytes'],peak_bytes=r['process_peak_bytes'],traffic_bytes=s['traffic']['total_bytes']))
guards=verify_blocks(completed,a8,al,ac,fixture=False)
need(len(guards)==6,'Block coverage differs')
# Recalculate guardrails directly from per-client records, rather than adapter.
for g in guards:
    base=next(r for m,r in completed if m['partition']==g['partition'] and m['seed']==g['seed'] and m['method']=='B')
    cs=base['metrics'][-1]['clients']; fm=base['metrics'][-1]['mean']
    own=dict(S1=all(c['occupied_clusters']>=2 and c['largest_cluster_fraction']<.99 for c in cs) and st.mean(c['largest_cluster_fraction'] for c in cs)<=.6,
             S2=all(sum(c['occupied_clusters']==1 for c in q['clients'])<=2 and st.mean(c['largest_cluster_fraction'] for c in q['clients'])<.9 for q in base['metrics']),
             Q1=fm['acc']>=.14 and fm['nmi']>=.01,Q2=base['round_records'][-1]['positive_relation_fraction']<=.6)
    own['passed']=all(own.values());need(all(g[k]==v for k,v in own.items()),'Independent guardrail differs')
with tempfile.TemporaryDirectory() as tmp:
    verdicts=reports(tmp,completed,guards,fixture=False,preset='full')
    for p in Path(tmp).iterdir(): need(p.read_bytes()==(R/p.name).read_bytes(),'Regenerated report differs: '+p.name)
need(verdicts==done['verdicts'],'Completion verdict differs')
lookup={(x['partition'],x['seed'],x['method'],x['repeat']):x for x in details}
paired=[]; independent={}
for part in ('iid','dirichlet_0.1'):
    rows=[]
    for seed in (1001,1002,1003):
        means={m:st.mean(lookup[part,seed,m,r]['head_seconds'] for r in range(3)) for m in ('B','E','D')}
        row=dict(partition=part,seed=seed,ratio_DB=means['D']/means['B'],ratio_DE=means['D']/means['E'],saved_DB=means['B']-means['D'],saved_DE=means['E']-means['D'])
        rows.append(row)
        for rep in range(3):
            d=lookup[part,seed,'D',rep];b=lookup[part,seed,'B',rep];e=lookup[part,seed,'E',rep]
            paired.append(dict(partition=part,seed=seed,repeat=rep,ratio_DB=d['head_seconds']/b['head_seconds'],ratio_DE=d['head_seconds']/e['head_seconds'],generation_ratio_DB=d['generation_seconds']/b['generation_seconds'],generation_ratio_DE=d['generation_seconds']/e['generation_seconds']))
    med_db=st.median(x['ratio_DB'] for x in rows);med_de=st.median(x['ratio_DE'] for x in rows)
    c1=med_db<=.9;c2=med_de<1;c3=sum(x['ratio_DB']<1 for x in rows)>=2 and sum(x['ratio_DE']<1 for x in rows)>=2
    v=verdicts[part];need(near(med_db,v['median_ratio_DB']) and near(med_de,v['median_ratio_DE']) and [c1,c2,c3,all((c1,c2,c3))]==[v['C1'],v['C2'],v['C3'],v['confirmed']],'Independent criteria differ')
    independent[part]=dict(rows=rows,median_ratio_DB=med_db,median_ratio_DE=med_de,C1=c1,C2=c2,C3=c3)
relations=sum(r['validation']['relation_comparisons'] for _,r in completed);candidates=sum(r['validation']['candidate_membership_comparisons'] for _,r in completed)
need(relations==done['relation_comparisons']==530841600 and candidates==done['candidate_membership_comparisons']==707788800 and done['mismatches']==0,'Oracle coverage differs')
OUT.mkdir(parents=True,exist_ok=True)
for name,data in [('run_details.csv',details),('repeat_pairs.csv',paired)]:
    with (OUT/name).open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
receipt=dict(result='PASS',files_verified=len(done['files']),source_hashes_verified=len(env['source_hashes']),runs=54,blocks=6,anchors_verified=16,relations=relations,candidates=candidates,mismatches=0,guards=guards,independent=independent,paired_wins_DB=sum(x['ratio_DB']<1 for x in paired),paired_wins_DE=sum(x['ratio_DE']<1 for x in paired),generation_wins_DB=sum(x['generation_ratio_DB']<1 for x in paired),generation_wins_DE=sum(x['generation_ratio_DE']<1 for x in paired),round_timing_flags=flags,power_start=env['started_power'],power_end=final['ended_power'],invocations=[read(p) for p in R.glob('invocation_*.json')],continuous_power_monitoring=False,excluded_timing=False,replayed_training=False)
(OUT/'audit.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(dict(result='PASS',files=receipt['files_verified'],runs=54,head_wins_DB=receipt['paired_wins_DB'],head_wins_DE=receipt['paired_wins_DE'],gen_wins_DE=receipt['generation_wins_DE'],timing_flags=flags),ensure_ascii=False))
