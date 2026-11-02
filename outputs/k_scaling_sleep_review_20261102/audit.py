import json,statistics as st
from datetime import datetime
from pathlib import Path
from experiments.k_scaling.run import environment_check,verify_record,verify_groups,non_time_rows
from experiments.k_scaling.design import plan,schedule,filename
from experiments.stl10_transfer.run import digest

ROOT=Path.cwd();R=ROOT/'experiments/k_scaling/results_full';O=ROOT/'outputs/k_scaling_sleep_review_20261102'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def need(ok,msg):
 if not ok:raise ValueError(msg)
env=read(R/'environment.json');environment_check(env)
final=read(R/'environment_final.json');environment_check(final)
done,finished=read(R/'completed.json'),read(R/'finished.json')
need(finished['status']=='complete' and digest(R/'completed.json')==finished['completed_manifest_sha256'],'Completion seal differs')
need(set(done['files'])=={str(p.relative_to(R)) for p in R.rglob('*') if p.is_file() and p.name not in ('completed.json','finished.json')},'Manifest coverage differs')
for p,sha in done['files'].items():need(digest(R/p)==sha,'Result bytes differ: '+p)
need(done['runs']==72 and done['memory_runs']==12,'Matrix count differs')
completed=[];phase_checks=[];flags=[];max_noninitial=0
for memory in (False,True):
 for m in schedule('full',memory):
  r=read(R/('memory' if memory else 'runs')/filename(m));spec=next(s for s in plan('full') if s.config.classes==m['classes'])
  entry=env['inputs'][f"{m['seed']}|{m['partition']}|{m['classes']}"]
  verify_record(r,m,spec,entry['base'],entry['pseudo'],memory,False)
  if memory:
   ref=next(v for meta,v in completed if all(meta[k]==m[k] for k in ('seed','partition','classes','method')))
   need(non_time_rows(ref)==non_time_rows(r),'Memory trajectory differs')
  else:completed.append((m,r))
  for phase in ('private','generation','exchange','public','pipeline'):
   rows=r['round_records'][1:] if phase in ('generation','pipeline') else r['round_records']
   values=[x[phase+'_seconds'] for x in rows];med=st.median(values);top=max(rows,key=lambda x:x[phase+'_seconds'])
   phase_checks.append(dict(file=filename(m),memory=memory,phase=phase,median=med,max_seconds=top[phase+'_seconds'],max_round=top['round'],max_ratio=top[phase+'_seconds']/med))
   for x in rows:
    if x[phase+'_seconds']>max(2,10*med):flags.append(dict(file=filename(m),memory=memory,phase=phase,round=x['round'],seconds=x[phase+'_seconds'],median=med))
  if not memory:max_noninitial=max(max_noninitial,max(x['pipeline_seconds'] for x in r['round_records'][1:]))
groups=verify_groups(completed);need(len(groups)==24,'Triple coverage differs')
events=read(O/'power_events.json');events=events if isinstance(events,list) else [events]
actual_events=[e for e in events if datetime.fromisoformat(e['Time']).timestamp()>=env['started_utc'] and datetime.fromisoformat(e['Time']).timestamp()<=final['ended_utc']]
exits=[dict(time=e['Time'],scenario=e['Data'].get('ScenarioInstanceIdV2'),sleep_entered=e['Data'].get('SleepEntered'),sleep_duration_us=e['Data'].get('SleepDurationInUs'),session_duration_us=e['Data'].get('DurationInUs')) for e in actual_events if e['Id']==507]
summary=dict(status='NO_IDENTIFIABLE_SLEEP_TIME_TO_EXCLUDE' if not flags else 'REQUIRES_CAUSAL_REVIEW',
             manifest_files_verified=len(done['files']),runs_verified=72,memory_runs_verified=12,triples_verified=24,
             run_start=datetime.fromtimestamp(env['started_utc']).isoformat(),run_end=datetime.fromtimestamp(final['ended_utc']).isoformat(),
             max_noninitial_pipeline_seconds=max_noninitial,statistical_flags=flags,
             phase_checks=phase_checks,power_exits=exits,actual_window_events=actual_events,
             excluded_rounds=[],excluded_runs=[],raw_results_changed=False,
             note='Confirmed user sleep actions do not identify timed method intervals. Screening is diagnostic, not automatic exclusion. No sleep duration is subtracted from head time without overlap evidence; original report remains the current report.')
prep_event=O/'preparation_sleep_event.json'
if prep_event.exists():
 key='1002|dirichlet_0.1|64'
 prep=read(Path(env['inputs'][key]['pseudo'])/'prepared_k.json')
 client=next(c for c in prep['clients'] if c['client']==3)
 need(client['incremental_kmeans_seconds']>600,'Expected confirmed preparation outlier missing')
 summary['status']='PREPARATION_SLEEP_CONTAMINATION_IDENTIFIED'
 summary['affected_preparation']=dict(seed=1002,partition='dirichlet_0.1',classes=64,client=3,
   kmeans_client_seconds=client['incremental_kmeans_seconds'],
   whole_additional_kmeans_seconds=prep['additional_kmeans_seconds'],
   whole_additional_preparation_seconds=prep['additional_preparation_seconds'],
   event=read(prep_event),action='Mark contaminated shared preparation and totals including it unavailable for all B/E/D; retain all method-stage times. No counterfactual time imputation.')
 summary['note']='Method-stage environment.started_utc is after preparation. Real preparation sleep found by extending analysis to small-cache timestamps. No numerical sleep subtraction is defensible.'
(O/'audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:summary[k] for k in ('status','manifest_files_verified','runs_verified','memory_runs_verified','max_noninitial_pipeline_seconds','statistical_flags','power_exits','excluded_rounds')},ensure_ascii=False))
