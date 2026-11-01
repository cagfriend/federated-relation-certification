import json
from pathlib import Path
import unittest
from threadpoolctl import threadpool_limits
from experiments.private_workload.design import spec_from_json
from experiments.public_scaling.data import Prepared
import experiments.private_workload.engine as original
from .run import drive,compare_anchor,ANCHOR_KEYS

class DiagnosticTests(unittest.TestCase):
 def setUp(self):
  self.limits=threadpool_limits(limits=1);self.limits.__enter__()
  root=Path(__file__).resolve().parents[2]
  source=root/'experiments/stl10_transfer/results_smoke_final'
  env=json.loads((source/'environment.json').read_text(encoding='utf-8'))
  self.spec=max((spec_from_json(s) for s in env['plan']),key=lambda s:s.config.samples)
  marker=json.loads((source/'prepared_iid_seed_1001.json').read_text(encoding='utf-8'))
  self.data=Prepared(marker['path'],self.spec.config,allow_test_fixture=True)
 def tearDown(self):
  self.data.close();self.limits.__exit__(None,None,None)
 def test_joint_matches_original_and_observers_do_not_change_updates(self):
  reference=original.WorkloadMethod('B',self.data,self.spec)
  rows=[reference.step(r)[0] for r in (1,2)]
  saved=(original.private_workload_epoch,original.update)
  observed,_=drive(self.data,self.spec,'J',2)
  quiet,_=drive(self.data,self.spec,'J',2,observations=False)
  self.assertEqual(saved,(original.private_workload_epoch,original.update))
  for base,a,b in zip(rows,observed['round_records'],quiet['round_records']):
   for key in ANCHOR_KEYS:self.assertEqual(base[key],a[key]);self.assertEqual(a[key],b[key])
 def test_fixed_round1_and_private_only_control(self):
  j,_=drive(self.data,self.spec,'J',2,observations=False)
  f,targets=drive(self.data,self.spec,'F',2,observations=False)
  p,_=drive(self.data,self.spec,'P',2,observations=False)
  self.assertEqual(j['round_records'][0]['head_digest_after_public'],f['round_records'][0]['head_digest_after_public'])
  for a,b in zip(f['round_records'][0]['student_targets'],f['round_records'][1]['student_targets']):
   self.assertEqual(a['digest'],b['digest']);self.assertEqual(b['changed_fraction_from_previous'],0.)
  self.assertTrue(all(t is not None for t in targets))
  for row in p['round_records']:
   self.assertEqual(row['public_optimizer_steps'],0);self.assertEqual(row['student_forward_endpoints'],0);self.assertEqual(row['public_edges_consumed'],0)
  head=original.WorkloadMethod('B',self.data,self.spec)
  for rnd in (1,2):
   for c,h in enumerate(head.heads):original.private_workload_epoch(h,self.data.private[c],self.data.pseudo[c],self.spec.config,self.data.seed,c,rnd,None)
  self.assertEqual(p['final_head_digest'],original.heads_digest(head.heads))
 def test_anchor_detects_trajectory_change(self):
  r,_=drive(self.data,self.spec,'J',1,observations=False)
  anchor=dict(initial_head_digest=r['initial_head_digest'],round_records=r['round_records'],metrics=[])
  compare_anchor(r,anchor)
  import copy
  bad=copy.deepcopy(anchor);bad['round_records'][0]['private_loss']+=1
  with self.assertRaises(AssertionError):compare_anchor(r,bad)

if __name__=='__main__':unittest.main()
