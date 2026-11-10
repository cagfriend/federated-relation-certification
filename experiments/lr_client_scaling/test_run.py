"""Regression checks for the new budget/dose and unchanged learning path."""
import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
import numpy as np
from threadpoolctl import threadpool_limits
from experiments.client_scaling.design import plan as old_plan
from experiments.client_scaling import data
from experiments.client_scaling.engine import run
from experiments.client_scaling.run import verify_record, verify_groups, non_time_rows
from experiments.noniid_clustering.data import partition_indices
from experiments.stl10_transfer.run import seal
from .design import plan, schedule, filename


class P3Tests(unittest.TestCase):
    def test_only_dose_changes_and_formal_capacity(self):
        jobs=schedule('full')
        self.assertEqual(len(jobs),54)
        self.assertEqual(len({filename(j) for j in jobs}),54)
        self.assertEqual(len(schedule('full',memory=True)),12)
        self.assertEqual({m:sum(j['position']==0 and j['method']==m for j in jobs) for m in ('B','E','D')},dict(B=6,E=6,D=6))
        for spec,old in zip(plan('full'),old_plan('full','fixed_per_client')):
            self.assertEqual(replace(spec,config=replace(spec.config,public_weight=1)).json(),old.json())
            cfg=spec.config;n=len(cfg.dimensions)
            self.assertEqual(cfg.head_lr*cfg.public_weight,.05)
            self.assertEqual(cfg.preparation(),old.config.preparation())
            for partition in ('iid','dirichlet_0.1'):
                total=cfg.train_limit-cfg.public_pool
                _,ids,_=partition_indices(np.arange(total)%10,0,n,1001,partition)
                self.assertEqual([len(v) for v in ids],[400]*n)
                np.testing.assert_array_equal(np.sort(np.concatenate(ids)),np.arange(total))

    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);p=Path(cls.tmp.name)
        spec=plan('smoke')[0];cls.spec=replace(spec,config=replace(spec.config,rounds=2))
        cls.directory=data.prepare(p/'prepared',p/'raw',cls.spec,1001,'iid',fixture=True)
        cls.records=[]
        with threadpool_limits(limits=1):
            for method in ('B','E','D'):
                meta=dict(seed=1001,partition='iid',regime='fixed_per_client',clients=2,method=method)
                r=run(cls.directory,cls.spec,method,fixture=True)
                r.update(meta,memory_mode=False,process_peak_bytes=0)
                cls.records.append((meta,seal(r)))
            cls.memory=run(cls.directory,cls.spec,'D',fixture=True,memory=True)

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_exact_trajectory_and_private_work(self):
        for m,r in self.records:
            verify_record(r,m,self.spec,self.directory,False,True)
            self.assertTrue(all(row['private_samples_per_client']==[32,32] for row in r['round_records']))
        verify_groups(self.records)
        self.assertEqual(non_time_rows(self.memory),non_time_rows(self.records[2][1]))

    def test_changed_work_or_public_dose_rejected(self):
        m,r=self.records[0];bad=copy.deepcopy(r)
        bad['round_records'][0]['private_samples_per_client'][0]+=1
        with self.assertRaisesRegex(ValueError,'Private workload'):
            verify_record(seal(bad),m,self.spec,self.directory,False,True)
        bad=copy.deepcopy(r);bad['config']['public_weight']=1
        with self.assertRaisesRegex(ValueError,'configuration'):
            verify_record(seal(bad),m,self.spec,self.directory,False,True)

    def test_report_quality_once_and_guard_wrong_protocol(self):
        from .report import reports
        import csv,json
        # The dose check must not silently label an old 0.1 run as P3.
        bad=copy.deepcopy(self.records);bad[0][1]['config']['public_weight']=1
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            with self.assertRaisesRegex(ValueError,'different learning protocol'):reports(t,bad,[],True)
            reports(t,self.records,[],True)
            scope=json.loads((Path(t)/'scope.json').read_text())
            self.assertEqual(scope['quality_trajectories'],1)
            self.assertEqual(scope['private_samples_per_client'],32)
            with (Path(t)/'quality_guardrails.csv').open(encoding='utf-8') as handle:
                rows=list(csv.DictReader(handle))
            self.assertEqual(len(rows),1)


if __name__=='__main__':unittest.main()
