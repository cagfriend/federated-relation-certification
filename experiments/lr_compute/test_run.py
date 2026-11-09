import copy
from pathlib import Path
import unittest
import csv
import tempfile
from experiments.collapse_intervention.run import read
from experiments.stl10_transfer.run import seal
from experiments.public_lr_confirmation import data as input_data
from experiments.k_scaling import data as k_data
from experiments.k_scaling.engine import run as engine_run
from threadpoolctl import threadpool_limits
from .design import plan, schedule
from .run import preparation, validate, compare_anchor


class ResourceTests(unittest.TestCase):
    def test_sparse_traffic_columns(self):
        from .report import _write
        scratch = Path(__file__).resolve().parent / 'test_artifacts'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as tmp:
            path = Path(tmp) / 'sparse.csv'
            _write(path, [dict(traffic_up_delta_messages=2, head=1),
                          dict(traffic_down_delta_messages=3, head=2)])
            with path.open(encoding='utf-8') as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]['traffic_down_delta_messages'], '0')
            self.assertEqual(rows[1]['traffic_up_delta_messages'], '0')

    def test_matrix(self):
        self.assertEqual(len(schedule('full')), 24)
        self.assertEqual(len(schedule('full', True)), 6)
        self.assertEqual(len(schedule('smoke')), 12)
        for spec in plan('full').values():
            self.assertEqual(spec.steps, 2)
            self.assertEqual(spec.config.head_lr * spec.config.public_weight, .05)
            self.assertEqual(spec.config.head_lr, .1)

    def test_legacy_preparation_contamination(self):
        marker = read('experiments/public_lr_confirmation/results_full/inputs/n6_k64_dirichlet_0.1_seed1002.json')
        info = preparation(marker, plan('full')['n6_k64_dirichlet_0.1_seed1002'])
        self.assertTrue(info['known_contamination'])
        self.assertIsNone(info['additional_seconds'])
        self.assertGreater(info['additional_seconds_raw'], 600)

    def test_k64_exact_anchor_and_audit(self):
        source = Path('outputs/public_lr_confirmation_review_20261106/smoke_final')
        meta = next(m for m in schedule('smoke') if m['family']=='n6_k64' and m['partition']=='iid' and m['method']=='D')
        spec = plan('smoke')[meta['case_id']]
        entry = read(source / 'inputs' / f"{meta['case_id']}.json")
        input_data.verify_input(entry, spec, fixture=True)
        with threadpool_limits(limits=1):
            r = engine_run(entry['base_directory'], spec, k_data.pseudo_paths(entry['k_directory']), method='D', fixture=True)
        r.update(study_case=meta['case_id'],family=meta['family'],role=meta['role'],partition=meta['partition'],method='D',
                 regime='fixed_total',clients=2,memory_mode=False)
        r['preparation']=preparation(entry,spec)
        p=r['preparation'];r['summary']['D']['with_shared_preparation_seconds']=p['base_seconds']+p['additional_seconds']+r['shared_loading_seconds']+r['summary']['D']['head_pipeline_seconds']
        validate(seal(r), meta, spec, entry, False, True)
        anchor=read(source/'records'/f"{meta['case_id']}_public2_half.json")['result']
        compare_anchor(r,anchor)
        broken=copy.deepcopy(r);broken['study_case']='wrong'
        with self.assertRaisesRegex(ValueError,'Study case'):
            validate(seal(broken),meta,spec,entry,False,True)


if __name__=='__main__':unittest.main()
