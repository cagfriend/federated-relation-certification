import copy
import unittest
from pathlib import Path
from experiments.lr_compute.run import read
from experiments.stl10_transfer.run import seal
from .design import plan, schedule, filename, criteria
from .run import validate, compare_method, verify_blocks


class RepeatTests(unittest.TestCase):
    def test_order_balance(self):
        jobs = schedule('full')
        self.assertEqual(len(jobs), 36)
        self.assertEqual(len({filename(m) for m in jobs}), 36)
        for cid in plan('full'):
            for method in ('B','E','D'):
                self.assertEqual(sorted(m['position'] for m in jobs if m['case_id']==cid and m['method']==method), [0,1,2])
        self.assertEqual(len(schedule('smoke')), 18)

    def test_threshold_boundaries(self):
        self.assertTrue(criteria([.9,.9,.95], [.97,.97,.99])['passed'])
        self.assertFalse(criteria([.9,.9,.95], [.971,.971,.99])['C2'])
        self.assertFalse(criteria([.9,1.1,1.1], [.96,.96,.96])['C3'])

    def test_counter_and_repeat_tampering(self):
        source=Path('outputs/lr_compute_review_20261106/smoke_v2')
        meta=schedule('smoke')[0]
        raw=read(source/'runs'/f"{meta['case_id']}_{meta['method']}.json")
        env=read(source/'environment.json');entry=env['inputs'][meta['case_id']]['entry']
        record=copy.deepcopy(raw);record.update(repeat=meta['repeat'],position=meta['position'])
        validate(seal(record),meta,plan('smoke')[meta['case_id']],entry,True)
        compare_method(record,raw)
        bad=copy.deepcopy(record);bad['repeat']=1
        with self.assertRaisesRegex(ValueError,'Repeat identity'):
            validate(seal(bad),meta,plan('smoke')[meta['case_id']],entry,True)
        bad=copy.deepcopy(record);bad['round_records'][0]['teacher_forward_endpoints']+=1
        with self.assertRaisesRegex(ValueError,'Method-specific counters'):
            compare_method(bad,raw)

    def test_duplicate_repetition_rejected(self):
        source=Path('outputs/lr_compute_review_20261106/smoke_v2')
        jobs=schedule('smoke')[:9]
        completed=[]
        for meta in jobs:
            raw=read(source/'runs'/f"{meta['case_id']}_{meta['method']}.json")
            completed.append((meta,raw))
        verify_blocks(completed)
        bad=list(completed);bad[-1]=bad[0]
        with self.assertRaisesRegex(ValueError,'Repeat composition'):
            verify_blocks(bad)


if __name__=='__main__':unittest.main()
