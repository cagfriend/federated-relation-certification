from dataclasses import replace
from pathlib import Path
import copy
import tempfile
import unittest
from threadpoolctl import threadpool_limits
from experiments.collapse_intervention.engine import drive
from experiments.collapse_intervention.run import check_reference
from experiments.private_workload.engine import WorkloadMethod
from experiments.public_scaling.engine import heads_digest
from . import data
from .design import cases, spec_for, verdict
from .run import envelope_check, history_path
from experiments.stl10_transfer.run import seal


class ConfirmationTests(unittest.TestCase):
    def test_matrix_and_reuse(self):
        matrix = cases('full')
        self.assertEqual(len(matrix), 8)
        self.assertEqual(sum(history_path(c, a, False) is None for c in matrix for a in ('reference2','public2_half')), 11)
        self.assertEqual(len({c['case_id'] for c in matrix}), 8)
        self.assertEqual({c['seed'] for c in matrix if c['role']=='new_seed'}, {1101})

    def test_guardrail_edges(self):
        clients=[dict(occupied_clusters=3,largest_cluster_fraction=.4) for _ in range(6)]
        record=dict(metrics=[dict(round=200,clients=clients,mean=dict(nmi=.02))])
        self.assertTrue(verdict(record)['passed'])
        clients[0]['largest_cluster_fraction']=.995
        self.assertFalse(verdict(record)['final_structure'])

    def test_both_target_loaders_and_lr(self):
        scratch=Path(__file__).resolve().parent/'test_artifacts';scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temp, threadpool_limits(limits=1):
            for family in ('n12_k10','n6_k64'):
                case=dict(family=family,seed=1001,partition='iid')
                spec=spec_for('smoke',family);spec=replace(spec,config=replace(spec.config,rounds=2))
                entry=data.prepare_input(temp,case,spec,fixture=True)
                prepared=data.load_input(entry,spec,fixture=True)
                try:
                    observed=drive(prepared,spec,'public2_half',observations=False)
                    half=replace(spec,config=replace(spec.config,public_weight=.5))
                    trainer=WorkloadMethod('B',prepared,half)
                    rows=[trainer.step(r)[0] for r in (1,2)]
                    expected=dict(initial_head_digest=observed['initial_head_digest'],graph_sha256=observed['graph_sha256'],round_records=rows,metrics=[])
                    check_reference(observed,expected)
                    self.assertEqual(observed['final_head_digest'],heads_digest(trainer.heads))
                    self.assertEqual(half.config.head_lr,spec.config.head_lr)
                finally:prepared.close()
                bad=copy.deepcopy(entry);bad['base_metadata_sha256']='invalid'
                with self.assertRaisesRegex(ValueError,'digest/fixture'):
                    data.verify_input(bad,spec,fixture=True)


if __name__=='__main__':unittest.main()
