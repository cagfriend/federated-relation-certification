from pathlib import Path
import sys,json
R=Path(__file__).resolve().parents[2];sys.path.insert(0,str(R))
from experiments.low_capacity_diagnostic.run import source_snapshot,read
from experiments.low_capacity_diagnostic.design import cases,source_key,plan,PROBE_SIZES
from experiments.low_capacity_diagnostic.probes import manifest
from experiments.quantity_heterogeneity import data
from experiments.stl10_transfer.run import digest
import numpy as np
source=R/'experiments/quantity_heterogeneity/results_full';snap=source_snapshot(source);env=read(source/'environment.json')
records=[]
for c in cases('full'):
 item=env['inputs'][source_key(c)];p=Path(item['path'])
 assert digest(p/'prepared.json')==item['metadata_sha256']
 data.verify(p,plan('full')['baseline'],c['seed'],c['partition'],profile='strong',fixture=False)
 probe=manifest(c['seed'],np.load(p/'public_ids.npy',allow_pickle=False),PROBE_SIZES['full'])
 assert probe['probe_size']==512
 old=read(source/'runs'/f"{c['partition']}_strong_seed{c['seed']}_B.json")
 assert len(old['round_records'])==200 and {20,40,160,180,200}.issubset({m['round'] for m in old['metrics']})
 records.append(dict(case_id=c['case_id'],metadata_sha256=item['metadata_sha256'],probe=probe))
 print('Verified read-only formal input: '+c['case_id'],flush=True)
dest=Path(__file__).parent/'formal_input_preflight.json';dest.write_text(json.dumps(dict(formal_training_started=False,source_snapshot=snap,cases=records),indent=2),encoding='utf-8')
print('Four original strong caches and historical checkpoints verified; no training/preparation started')
