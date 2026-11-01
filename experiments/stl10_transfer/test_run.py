import copy,unittest
from experiments.stl10_transfer.run import check_run,seal
from experiments.stl10_transfer.report import aggregate

class RunValidationTests(unittest.TestCase):
 def fixture_run(self,method='B'):
  return dict(run_sha256='',seed=1,partition='iid',method=method,case_id='x',dataset='STL-10 fixture',
   spec={'case_id':'x','config':{'samples':2}},prepared_directory='cache',round_records=[dict(round=1,pipeline_seconds=2.,private_seconds=0.,generation_seconds=0.,exchange_seconds=0.,public_seconds=0.)],
   summary={method:dict(initialization_seconds=1.,head_pipeline_seconds=3.,with_shared_preparation_seconds=4.,generation_seconds=0.,private_seconds=0.,exchange_seconds=0.,public_seconds=0.,persistent_method_array_bytes=0,final_metrics={'mean':{'acc':.5,'nmi':.4,'ari':.3}})},
   validation=dict(enabled=True,mismatches=0,relation_comparisons=1,candidate_membership_comparisons=0),coverage_records=[dict(round=1)])
 def test_seal_detects_tampering(self):
  r=seal(self.fixture_run());self.assertEqual(r['run_sha256'],seal(copy.deepcopy(r))['run_sha256'])
  r['seed']=2
  with self.assertRaises(ValueError):
   # seal content check uses exact canonical payload
   check_run(r,dict(seed=1,partition='iid',method='B',case_id='x'),type('Spec',(),{'json':lambda _: {'case_id':'x'},'config':type('C',(),{'rounds':1,'dimensions':[1],'samples':2,'degree':1})()})(),__import__('pathlib').Path('cache'),True)
 def test_report_uses_seed_pairs_and_no_implicit_decision(self):
  rs=[]
  for m,t in [('B',4.),('E',3.),('D',2.)]:
   x=self.fixture_run(m);x.update(run_sha256='',seed=1,partition='iid',case_id='m1',dataset='STL-10 fixture',prepared_directory='cache');x['spec']={'case_id':'m1','config':{'samples':2}};x['round_records'][0]['pipeline_seconds']=t-1;x['summary'][m]['head_pipeline_seconds']=t;x=seal(x);rs.append(x)
  rows,paired,summ,quality=aggregate(rs);self.assertEqual(len(paired),2);self.assertEqual(len(summ),2);self.assertEqual(quality,[])
  self.assertEqual(next(x for x in summ if x['comparison']=='D/B')['head_wins'],1)
 def test_cross_m_guardrail_is_seed_level_sensitivity(self):
  rs=[]
  for samples,case,acc in ((128,'m128',.50),(32,'m32',.495)):
   for method in ('B','E','D'):
    x=self.fixture_run(method);x.update(seed=1,partition='iid',case_id=case,dataset='STL-10 fixture')
    x['spec']={'case_id':case,'config':{'samples':samples}};x['summary'][method]['final_metrics']['mean']['acc']=acc
    rs.append(seal(x))
  _,_,_,quality=aggregate(rs)
  self.assertEqual(quality[0]['M_low'],32);self.assertEqual(quality[0]['M_high'],128)
  self.assertTrue(quality[0]['within_1pp']);self.assertAlmostEqual(quality[0]['change_high_minus_low'],.005)

if __name__=='__main__':unittest.main()
