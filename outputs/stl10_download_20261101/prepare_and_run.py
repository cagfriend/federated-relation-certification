"""Separate resumable acquisition from the frozen experiment; start only after official validation."""
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from experiments.stl10_transfer.data import URL, TARBALL_MD5, ensure_data, md5
from experiments.stl10_transfer.run import check_environment, power_status

HERE=Path(__file__).parent
DATA=ROOT/'experiments/stl10_transfer/data'
ARCHIVE=DATA/'stl10_binary.tar.gz'
OLD_PART=DATA/'stl10_binary.tar.gz.part'
PARTS=HERE/'parts'
SIZE=2640397119
CHUNK=32*1024*1024
WORKERS=12

def say(s): print(time.strftime('%H:%M:%S')+' '+s,flush=True)
def part_path(i):return PARTS/f'{i:04d}.bin'
def get_chunk(i):
    start=i*CHUNK;end=min(SIZE,start+CHUNK)-1;p=part_path(i);length=end-start+1
    if p.is_file() and p.stat().st_size==length:return i
    temp=p.with_suffix('.downloading')
    curl=shutil.which('curl.exe')
    if not curl:raise RuntimeError('curl.exe unavailable')
    for attempt in range(5):
        cmd=[curl,'--fail','--silent','--show-error','--location','--connect-timeout','20','--max-time','1200','--speed-time','90','--speed-limit','1024','--range',f'{start}-{end}','--output',str(temp),URL]
        r=subprocess.run(cmd,capture_output=True,text=True)
        if r.returncode==0 and temp.exists() and temp.stat().st_size==length:
            temp.replace(p);return i
        say(f'Chunk {i} retry {attempt+1}: curl={r.returncode}, bytes={temp.stat().st_size if temp.exists() else 0}, error={r.stderr[-200:]}')
        time.sleep(2)
    raise RuntimeError(f'Chunk {i} failed')

def main():
    DATA.mkdir(exist_ok=True,parents=True);PARTS.mkdir(exist_ok=True,parents=True)
    if not ARCHIVE.exists():
        # Preserve the user's partial stream. Reuse its complete leading blocks;
        # the official whole-archive checksum remains the acceptance criterion.
        if OLD_PART.exists():
            with OLD_PART.open('rb') as f:
                for i in range(OLD_PART.stat().st_size//CHUNK):
                    p=part_path(i);block=f.read(CHUNK)
                    if not p.exists():p.write_bytes(block)
        total=(SIZE+CHUNK-1)//CHUNK
        say(f'Downloading {total} ranges, {WORKERS} connections; archive {SIZE} bytes')
        done=set()
        with cf.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures=[pool.submit(get_chunk,i) for i in range(total)]
            pending=set(futures)
            while pending:
                finished,pending=cf.wait(pending,timeout=20,return_when=cf.FIRST_COMPLETED)
                for f in finished:done.add(f.result())
                complete=sum(part_path(i).stat().st_size for i in done)
                inflight=sum(p.stat().st_size for p in PARTS.glob('*.downloading') if p.is_file())
                say(f'Progress {complete/1e6:.1f} MB complete + {inflight/1e6:.1f} MB receiving / {SIZE/1e6:.1f} MB; chunks {len(done)}/{total}')
        merged=HERE/'assembled.tar.gz'
        say('Assembling and checking official MD5')
        with merged.open('wb') as out:
            for i in range(total):
                with part_path(i).open('rb') as f:shutil.copyfileobj(f,out,1024*1024)
        actual=md5(merged)
        if merged.stat().st_size!=SIZE or actual!=TARBALL_MD5:
            raise RuntimeError(f'Archive rejected: size={merged.stat().st_size}, md5={actual}')
        merged.replace(ARCHIVE)
    if md5(ARCHIVE)!=TARBALL_MD5:raise RuntimeError('Existing archive checksum mismatch')
    say('Archive verified; extracting and validating all five official data files')
    started=time.time();base=ensure_data(DATA,download=False)
    receipt=dict(archive=str(ARCHIVE),archive_bytes=SIZE,archive_md5=md5(ARCHIVE),official_members_validated=True,data_directory=str(base),ready_utc=time.time(),extraction_and_validation_seconds=time.time()-started)
    (HERE/'DATA_READY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    say('Data ready. Checking frozen experiment and AC power before launch')
    envpath=ROOT/'experiments/stl10_transfer/results_full/environment.json'
    if envpath.exists():check_environment(json.loads(envpath.read_text(encoding='utf-8')))
    power=power_status()
    if power['ac_line_status']!=1:raise RuntimeError('Data ready, but experiment requires AC power; no training started')
    cmd=[sys.executable,'-u','-m','experiments.stl10_transfer.run']
    if envpath.exists():cmd+=['--resume']
    else:cmd+=['--preset','full','--prepare-device','cuda']
    receipt.update(training_command=cmd,training_start_utc=time.time(),power_at_launch=power)
    (HERE/'DATA_READY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    say('Starting formal experiment; preparation may take time before the first Running line')
    with (HERE/'experiment.log').open('a',encoding='utf-8',buffering=1) as log:
        p=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',env={**os.environ,'PYTHONIOENCODING':'utf-8'})
        (HERE/'training_pid.txt').write_text(str(p.pid),encoding='ascii')
        for line in p.stdout:print(line,end='',flush=True);log.write(line)
        code=p.wait()
    receipt.update(training_exit_code=code,training_end_utc=time.time())
    (HERE/'DATA_READY.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    if code:raise RuntimeError(f'Experiment exited {code}; see experiment.log')
    say('Formal experiment finished')

if __name__=='__main__':main()
