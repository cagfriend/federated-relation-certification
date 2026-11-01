"""Controlled-environment diagnostic pair; preserve preregistered data."""
import sys,subprocess,json
from pathlib import Path
R=Path(__file__).resolve().parents[2]
source=(R/'outputs/perf_confirmation_normal_rerun_20261101/rerun.py').read_text(encoding='utf-8')
for seed in (909,808):
 directory=R/f'outputs/perf_controlled_seed{seed}_20261101'
 directory.mkdir(exist_ok=True)
 script=directory/'rerun.py'
 if not script.exists():script.write_text(source.replace('808',str(seed)).replace('previously normal triple','controlled-environment diagnostic triple'),encoding='utf-8')
 print(f'Start controlled seed {seed}',flush=True)
 subprocess.run([sys.executable,str(script)],cwd=R,check=True)
print('Finished controlled pair',flush=True)
