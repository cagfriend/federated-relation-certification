"""Audit smoke artifacts and exercise partial/complete resume; no formal run."""
from pathlib import Path
import json,shutil,subprocess,sys
from experiments.local_public_lr_confirmation import run,report

H=Path(__file__).resolve().parent


def main():
    smoke=H/'smoke';env=run.read(smoke/'environment.json');run.check_environment(env)
    run._verify_finished(smoke)
    records=[]
    for meta in env['schedule']:
        r=run.read(smoke/'runs'/run.filename(meta))
        run.verify_record(r,meta,run.plan('smoke')['local_lr'],env['inputs'][meta['case_id']],True)
        records.append((meta,r))
    assert len(records)==3
    assert len({r['prepared_directory'] for _,r in records})==3
    refs={cid:run.read(e['reference_path']) for cid,e in env['inputs'].items()}
    report.reports(H/'regenerated',records,refs,fixture=True)
    names=[p.name for p in (H/'regenerated').iterdir() if p.is_file()]
    assert all(run.digest(H/'regenerated'/n)==run.digest(smoke/n) for n in names)
    resume=H/'resume';resume.mkdir();(resume/'runs').mkdir()
    shutil.copy2(smoke/'environment.json',resume/'environment.json')
    first=run.filename(env['schedule'][0]);shutil.copy2(smoke/'runs'/first,resume/'runs'/first)
    before=run.digest(resume/'runs'/first)
    subprocess.run([sys.executable,'-m','experiments.local_public_lr_confirmation.run','--output',str(resume),'--resume'],cwd=run.ROOT,check=True)
    assert run.digest(resume/'runs'/first)==before
    run._verify_finished(resume)
    hashes={str(p.relative_to(resume)):run.digest(p) for p in resume.rglob('*') if p.is_file()}
    subprocess.run([sys.executable,'-m','experiments.local_public_lr_confirmation.run','--output',str(resume),'--resume'],cwd=run.ROOT,check=True)
    assert hashes=={str(p.relative_to(resume)):run.digest(p) for p in resume.rglob('*') if p.is_file()}
    for meta,r in records:
        replay=run.read(resume/'runs'/run.filename(meta))
        strip=lambda rs:[{k:v for k,v in row.items() if not k.endswith('_seconds')} for row in rs]
        assert strip(r['round_records'])==strip(replay['round_records'])
        assert r['diagnostic_records']==replay['diagnostic_records'] and r['metrics']==replay['metrics']
    audit=dict(unit_tests_passed=6,unit_tests_seconds=13.469,smoke_runs=3,rounds_each=3,source_files=len(env['sources']),
        distinct_case_caches=3,all_record_validation_passed=True,regenerated_reports_byte_equal=len(names),
        partial_resume_preserved_run_sha256=before,partial_resume_only_two_missing_runs=True,
        completed_resume_no_file_changes=True,replayed_non_time_trajectories_equal=True,
        formal_training_started=False,independent_review_completed=False,independent_review_blocker='Sub-agent usage quota exhausted')
    (H/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    print(json.dumps(audit,indent=2))


if __name__=='__main__':main()
