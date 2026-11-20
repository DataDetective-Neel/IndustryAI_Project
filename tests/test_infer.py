import unittest
import hashlib
import tempfile
from pathlib import Path
from unittest.mock import patch

import numpy as np

from pcb_landmarks.infer import LandmarkDetector, assess


class InferenceTests(unittest.TestCase):
    def test_order_pixels_confidence_and_failures(self):
        names = ['upper_left', 'upper_right', 'lower_right', 'lower_left']
        points = np.array([[10, 10, .9], [80, 10, .9], [80, 90, .9], [10, 90, .9]])
        result = assess([[0, 0, 99, 99]], [.9], [points], names, (100, 100), .5, .7)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual([p['name'] for p in result['landmarks']], names)
        self.assertEqual(result['landmarks'][2]['x'], 80)
        for bad in [points * np.nan, points[:3], points * [1, 1, .1],
                    points * [20, 1, 1], np.tile(points[0], (4, 1))]:
            result = assess([[0, 0, 99, 99]], [.9], [bad], names, (100, 100), .5, .7)
            self.assertEqual(result['status'], 'failure')
            self.assertEqual(result['landmarks'], [])
        self.assertEqual(assess([], [], [], names, (100, 100), .5, .7)['status'], 'failure')
        self.assertEqual(assess([[0, 0, 99, 99]], [.5], [points], names, (100, 100), .5, .7)['status'], 'failure')
        self.assertEqual(assess([[0]*4]*2, [.9]*2, [points]*2, names, (100, 100), .5, .7)['reason'], 'ambiguous_boards')

    def test_invalid_cyclic_geometry_and_clipped_holes_fail(self):
        points = np.array([[10, 10, .9], [80, 10, .9], [80, 90, .9], [10, 90, .9]])
        collinear = points.copy()
        collinear[:, 1] = 10
        clipped = points.copy()
        clipped[0, 0] = 0
        for bad in [collinear, points[[0, 2, 1, 3]], points[[0, 3, 2, 1]], clipped]:
            result = assess([[0, 0, 99, 99]], [.9], [bad], ['a', 'b', 'c', 'd'], (100, 100), .5, .7)
            self.assertEqual(result['status'], 'failure')

    def test_mismatched_hash_rejected_before_model_deserialization(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'bad.pt'
            path.write_bytes(b'not the approved checkpoint')
            with patch('ultralytics.YOLO') as yolo:
                with self.assertRaisesRegex(ValueError, 'hash'):
                    LandmarkDetector(path, expected_sha256=hashlib.sha256(b'approved bytes').hexdigest())
                yolo.assert_not_called()

    def test_missing_checkpoint_fails_before_yolo_or_network(self):
        with patch('socket.socket', side_effect=AssertionError('Network forbidden')):
            with self.assertRaises(FileNotFoundError):
                LandmarkDetector('not-a-local-model.pt', 'PCB_Dataset_Pilot/dataset.yaml')


if __name__ == '__main__':
    unittest.main()
