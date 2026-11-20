import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pcb_landmarks.train import main


class TrainingTests(unittest.TestCase):
    def test_checkpoint_is_written_in_requested_project(self):
        def train(**settings):
            self.assertTrue(Path(settings['project']).is_absolute())
            self.assertEqual(settings['fliplr'], 0)
            self.assertEqual(settings['flipud'], 0)
            weights = Path(settings['project']) / settings['name'] / 'weights'
            weights.mkdir()
            for name in ['best.pt', 'last.pt']:
                (weights / name).write_bytes(b'test')
            return SimpleNamespace(results_dict={})

        with tempfile.TemporaryDirectory(dir='.') as folder:
            project = Path(folder).relative_to(Path.cwd()) if Path(folder).is_absolute() else Path(folder)
            with patch('sys.argv', ['train', '--project', str(project), '--name', 'smoke']), \
                 patch('pcb_landmarks.train.audit', return_value={}), \
                 patch('ultralytics.YOLO') as yolo:
                yolo.return_value.train.side_effect = train
                main()
            self.assertTrue((project / 'smoke/summary.json').is_file())
