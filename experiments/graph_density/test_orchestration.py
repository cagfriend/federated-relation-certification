"""Focused checks for pairing and non-mutating preflight protection."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from .analyze import paired
from .run import main, preflight


class Tests(unittest.TestCase):
    def test_pair_before_taking_medians(self):
        cases = [dict(seed=i, summary={'B':{'t':b},'D':{'t':d}})
                 for i,(b,d) in enumerate(((10,9),(100,50),(20,1)))]
        result = paired(cases,'B','t')
        self.assertEqual(result['percent_less'],50)
        self.assertEqual(result['seconds_saved'],19)
        self.assertEqual(result['wins'],3)
        self.assertEqual([p['seed'] for p in result['raw_pairs']],[0,1,2])

    def test_never_use_reference_as_output_or_parent(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            root = Path(tmp)
            for reference,output in ((root,root),(root,root/'child'),(root/'child',root)):
                with self.assertRaises(ValueError):
                    preflight(reference,output)
            self.assertEqual(list(root.iterdir()),[])

    def test_check_only_does_not_start_training_or_write(self):
        from experiments.public_scaling.config import make_plan,preset
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            output = Path(tmp)/'new'
            with patch('sys.argv',['graph_density','--check-only','--output',str(output)]), \
                 patch('experiments.graph_density.run.preflight',return_value=make_plan(preset('full'),'graph')), \
                 patch('experiments.graph_density.run.subprocess.run') as child, \
                 patch('experiments.graph_density.run.analyze') as report:
                main()
            child.assert_not_called()
            report.assert_not_called()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
