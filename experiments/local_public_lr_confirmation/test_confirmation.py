"""Tests of new scheduling, record identities and confirmation reporting."""
import copy
import csv
import tempfile
import unittest
from pathlib import Path

from threadpoolctl import threadpool_limits
from experiments.local_public_lr import engine as shared_engine
from experiments.quantity_heterogeneity import data
from experiments.local_public_lr_confirmation import design, engine, report, run


class ConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='confirmation-',dir=run.DIR)
        cls.root=Path(cls.temp.name);cls.records=[];cls.spec=design.plan('smoke')['local_lr']
        for meta in design.schedule('smoke'):
            directory=data.prepare(cls.root/'cache',cls.root/'fixture',cls.spec,meta['seed'],meta['partition'],profile='strong',fixture=True)
            with threadpool_limits(limits=1):
                record=engine.run(directory,cls.spec,branch='local_lr',fixture=True,progress=False)
            cls.records.append((meta,run.seal(record)))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_matrix_and_exact_engine_reuse(self):
        wanted={(1001,'dirichlet_0.1'),(1002,'iid'),(1002,'dirichlet_0.1')}
        self.assertIs(engine.run,shared_engine.run)
        for preset,n,ev in [('full',200,20),('smoke',3,1)]:
            jobs=design.schedule(preset)
            self.assertEqual({(m['seed'],m['partition']) for m in jobs},wanted)
            self.assertEqual(len(jobs),3)
            self.assertTrue(all(m['branch']=='local_lr' for m in jobs))
            spec=design.plan(preset)['local_lr']
            self.assertEqual((spec.config.rounds,spec.config.eval_every,spec.effective_steps),(n,ev,2))
        self.assertEqual(design.client_weights(),[.125,.5,.5,.125,.5,.5])

    def test_three_real_fixture_identities_and_wrong_cache_rejected(self):
        paths=[]
        for meta,r in self.records:
            entry=dict(path=r['prepared_directory'],probe_manifest=r['probe_manifest'])
            self.assertTrue(run.verify_record(r,meta,self.spec,entry,True))
            self.assertEqual((r['seed'],r['partition']),(meta['seed'],meta['partition']))
            paths.append(entry['path'])
        self.assertEqual(len(set(paths)),3)
        meta,r=self.records[0];other=self.records[1][1]
        with self.assertRaises(ValueError):
            run.verify_record(r,meta,self.spec,dict(path=other['prepared_directory'],probe_manifest=other['probe_manifest']),True)
        broken=copy.deepcopy(r);broken['public_client_weights']=[.5]*6
        with self.assertRaises(ValueError):
            run.verify_record(run.seal(broken),meta,self.spec,dict(path=r['prepared_directory'],probe_manifest=r['probe_manifest']),True)

    def healthy_mock(self):
        """Synthetic report-only records, not scientific observations."""
        pairs=copy.deepcopy(self.records)
        for _,r in pairs:
            for metric,diag,rnd in zip(r['metrics'],r['diagnostic_records'],(160,180,200)):
                metric['round']=diag['round']=rnd
                for c in metric['clients']:
                    c.update(occupied_clusters=2,largest_cluster_fraction=.6,nmi=.1)
        return pairs

    def test_recovery_missing_and_exact_threshold_fail(self):
        _,r=self.healthy_mock()[0]
        self.assertTrue(report.recovery(r)['passed'])
        broken=copy.deepcopy(r);broken['metrics'][1]['clients'].pop()
        self.assertFalse(report.recovery(broken)['passed'])
        broken=copy.deepcopy(r);broken['metrics'].pop()
        self.assertFalse(report.recovery(broken)['passed'])
        r['metrics'][0]['clients'][0]['largest_cluster_fraction']=.99
        self.assertFalse(report.recovery(r)['passed'])

    def test_report_three_case_denominator_and_missing_case(self):
        pairs=self.healthy_mock()
        result=report.reports(self.root/'report_all',pairs,{},fixture=False)
        self.assertTrue(result['all_cases_released'])
        self.assertEqual(result['released_case_count'],3)
        self.assertEqual(result['counts'],dict(new_local_lr_runs=3,new_baseline_runs=0))
        result=report.reports(self.root/'report_missing',pairs[:2],{},fixture=False)
        self.assertFalse(result['all_cases_released'])
        self.assertEqual(len(result['expected_case_ids']),3)
        with (self.root/'report_all/recovery.csv').open(encoding='utf-8') as f:
            self.assertEqual(len(list(csv.DictReader(f))),54)

    def test_exploratory_or_duplicate_not_counted_as_confirmation(self):
        pairs=self.healthy_mock()
        with self.assertRaises(ValueError):
            report.reports(self.root/'bad_duplicate',pairs+[pairs[0]],{},fixture=False)
        pairs[0][0]['case_id']='strong_iid_seed1001'
        with self.assertRaises(ValueError):
            report.reports(self.root/'bad_exploration',pairs,{},fixture=False)

    def test_historical_late_stage_na_and_events_retained(self):
        pairs=self.healthy_mock();cid=pairs[0][0]['case_id']
        historical=copy.deepcopy(pairs[0][1]);historical['metrics']=historical['metrics'][:1]
        historical['metrics'][0]['round']=20
        historical['diagnostic_records']=historical['diagnostic_records'][:1]
        historical['diagnostic_records'][0]['round']=20
        exploratory=copy.deepcopy(pairs[0][1])
        pairs[0][1]['metrics'][0]['clients'][0].update(occupied_clusters=1,largest_cluster_fraction=1.)
        target=self.root/'report_history'
        result=report.reports(target,pairs,{cid:{'metrics':historical['metrics']}},fixture=False,
            history=dict(low_capacity={(cid,'baseline'):historical},prior_local={'local_lr':exploratory}))
        self.assertFalse(result['all_cases_released'])
        self.assertEqual(result['counts']['new_local_lr_runs'],3)
        with (target/'historical_stage_availability.csv').open(encoding='utf-8') as f:
            baseline=[r for r in csv.DictReader(f) if r['source']=='low_capacity_baseline']
        self.assertEqual(len(baseline),9)
        self.assertTrue(all(r['value']=='NA' and r['available']=='False' for r in baseline))
        with (target/'historical_test_metrics.csv').open(encoding='utf-8') as f:
            baseline=[r for r in csv.DictReader(f) if r['source']=='low_capacity_baseline']
        self.assertEqual({r['round'] for r in baseline},{'20'})
        with (target/'test_severe_events.csv').open(encoding='utf-8') as f:
            self.assertEqual(len(list(csv.DictReader(f))),1)


if __name__=='__main__':unittest.main()
