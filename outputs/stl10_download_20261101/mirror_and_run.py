"""Acquire raw STL-10 members from ModelScope, require official MD5s, then resume."""
import concurrent.futures as cf
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.stl10_transfer.data import FILES, md5, ensure_data
from experiments.stl10_transfer.run import check_environment, power_status
HERE=Path(__file__).parent
BASE=ROOT/'experiments/stl10_transfer/data/stl10_binary'
PARTS=HERE/'mirror_parts'
SIZES={'train_X.bin':138240000,'train_y.bin':5000,'test_X.bin':221184000,'test_y.bin':8000,'unlabeled_X.bin':2764800000}
CHUNK=8*1024*1024
URL='https://modelscope.cn/api/v1/datasets/kxs712/STL10/repo?Revision=master&FilePath='
def say(s):print(time.strftime('%H:%M:%S')+' '+s,flush=True)
def fetch(task):
 name,i=task;start=i*CHUNK;end=min(SIZES[name],start+CHUNK)-1;size=end-start+1
 p=PARTS/f'{name}.{i:04d}'
 if p.exists() and p.stat().st_size==size:return size
 temp=p.with_suffix(p.suffix+'.part')
 for attempt in range(6):
  r=subprocess.run(['curl.exe','--fail','--silent','--show-error','--location','--connect-timeout','15','--max-time','600','--range',f'{start}-{end}','--output',str(temp),'--write-out','%{http_code}',URL+name],capture_output=True,text=True)
  if r.returncode==0 and r.stdout.strip()=='206' and temp.exists() and temp.stat().st_size==size:
   temp.replace(p);return size
  say(f'Retry {name}:{i} ({attempt+1}): curl={r.returncode}, HTTP={r.stdout.strip()} {r.stderr[-150:]}');time.sleep(3)
 raise RuntimeError(f'Download failed: {task}')
def main():
 BASE.mkdir(parents=True,exist_ok=True);PARTS.mkdir(exist_ok=True)
 needed=[n for n in FILES if not (BASE/n).exists() or md5(BASE/n)!=FILES[n]]
 tasks=[(n,i) for n in needed for i in range((SIZES[n]+CHUNK-1)//CHUNK)]
 total=sum(SIZES[n] for n in needed);complete=0
 say(f'ModelScope raw files: {len(tasks)} ranges, 12 connections, {total/1e6:.1f} MB')
 with cf.ThreadPoolExecutor(max_workers=12) as pool:
  pending={pool.submit(fetch,t) for t in tasks}
  while pending:
   done,pending=cf.wait(pending,timeout=20,return_when=cf.FIRST_COMPLETED)
   for f in done:complete+=f.result()
   if not done or len(pending)%12==0:say(f'Complete {complete/1e6:.1f}/{total/1e6:.1f} MB; remaining chunks {len(pending)}')
 for name in needed:
  temp=BASE/(name+'.assembling')
  with temp.open('wb') as out:
   for i in range((SIZES[name]+CHUNK-1)//CHUNK):
    with (PARTS/f'{name}.{i:04d}').open('rb') as f:shutil.copyfileobj(f,out,1024*1024)
  actual=md5(temp)
  if actual!=FILES[name]:raise RuntimeError(f'Official MD5 mismatch: {name}: {actual}; no training started')
  temp.replace(BASE/name);say('Official checksum passed: '+name)
 ensure_data(BASE.parent,download=False)
 receipt=dict(source='https://modelscope.cn/datasets/kxs712/STL10',official_members_validated={n:md5(BASE/n) for n in FILES},data_ready_utc=time.time(),acquisition_wall_seconds=time.time()-START)
 (HERE/'DATA_READY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 envpath=ROOT/'experiments/stl10_transfer/results_full/environment.json'
 check_environment(json.loads(envpath.read_text(encoding='utf-8')))
 if power_status()['ac_line_status']!=1:raise RuntimeError('Data ready; AC power needed before training')
 say('All official data verified. Resuming frozen formal experiment.')
 cmd=[sys.executable,'-u','-m','experiments.stl10_transfer.run','--resume']
 with (HERE/'experiment.log').open('a',encoding='utf-8',buffering=1) as log:
  p=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
  (HERE/'training_pid.txt').write_text(str(p.pid),encoding='ascii')
  for line in p.stdout:print(line,end='',flush=True);log.write(line)
  code=p.wait()
 receipt.update(training_exit_code=code,training_end_utc=time.time())
 (HERE/'DATA_READY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
 if code:raise RuntimeError(f'Experiment exited {code}')
if __name__=='__main__':
 START=time.time();main()
