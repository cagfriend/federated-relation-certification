from dataclasses import replace
import unittest
from experiments.stl10_diagnostics.test_run import DiagnosticTests
from experiments.stl10_diagnostics.run import drive
from experiments.public_budget.student import selected_edges
from .run import budgets,validate

class PublicBudgetTests(unittest.TestCase):
 setUp=DiagnosticTests.setUp
 tearDown=DiagnosticTests.tearDown
 def test_budget_counts_and_common_first_teacher(self):
  results=[]
  for steps in budgets('smoke'):
   spec=replace(self.spec,steps=steps);spec.validate()
   r,_=drive(self.data,spec,'J',2,observations=False);validate(r,spec,2);results.append(r)
  self.assertEqual(len({r['initial_head_digest'] for r in results}),1)
  self.assertEqual(len({r['round_records'][0]['committed_counts_digest'] for r in results}),1)
  for r in results:
   for a,b in zip(r['round_records'],results[0]['round_records']):
    self.assertEqual(a['private_subset_digest'],b['private_subset_digest']);self.assertEqual(a['private_optimizer_steps'],b['private_optimizer_steps'])
 def test_edge_batches_are_nested_prefixes_of_same_graph(self):
  large=selected_edges(replace(self.spec,steps=4),1001,0,2)
  for steps in (1,2):
   small=selected_edges(replace(self.spec,steps=steps),1001,0,2)
   self.assertEqual(small.tolist(),large[:steps*self.spec.config.public_edge_batch].tolist())
 def test_counter_validation_rejects_wrong_public_budget(self):
  r,_=drive(self.data,self.spec,'J',1,observations=False)
  r['round_records'][0]['public_optimizer_steps']+=1
  with self.assertRaises(ValueError):validate(r,self.spec,1)

if __name__=='__main__':unittest.main()
