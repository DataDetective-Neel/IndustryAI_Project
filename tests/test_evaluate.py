import unittest

import numpy as np

from pcb_landmarks.evaluate import summarize, select_thresholds


class EvaluationTests(unittest.TestCase):
    def records(self):
        points = np.array([[10, 10, .9], [80, 10, .9], [80, 90, .9], [10, 90, .9]])
        return [dict(image='a.jpg', size=(100, 100), gt_box=np.array([0, 0, 99, 99]),
                     gt_points=points * [1, 1, 0] + [0, 0, 2],
                     boxes=np.array([[0, 0, 99, 99]]), scores=np.array([.8]), points=np.array([points]))]

    def test_pixel_errors_and_failure_denominators(self):
        records = self.records()
        result = summarize(records, ['a', 'b', 'c', 'd'], .5, .7, .01)
        self.assertEqual(result['all_four_usable'], 1)
        self.assertEqual(result['all_four_within_tolerance'], 1)
        self.assertEqual(result['per_landmark']['a']['mean_px'], 0)
        records[0]['points'][0, 2, 0] += 10
        result = summarize(records, ['a', 'b', 'c', 'd'], .5, .7, .01)
        self.assertEqual(result['all_four_usable'], 1)
        self.assertEqual(result['all_four_within_tolerance'], 0)
        self.assertEqual(result['per_landmark']['c']['mean_px'], 10)
        records[0]['scores'][:] = .1
        result = summarize(records, ['a', 'b', 'c', 'd'], .5, .7, .01)
        self.assertEqual(result['failed_detections'], 1)
        self.assertEqual(result['matched_predictions'], 1)
        records[0]['scores'][:] = .0001
        result = summarize(records, ['a', 'b', 'c', 'd'], .5, .7, .01)
        self.assertEqual(result['matched_predictions'], 0)
        self.assertIsNone(result['per_landmark']['a']['mean_px'])

    def test_validation_selection_penalizes_confident_wrong_points(self):
        records = self.records()
        records[0]['points'][0, 0, 0] += 30
        selection = select_thresholds(records, ['a', 'b', 'c', 'd'], .01)
        self.assertEqual(selection['summary']['confident_but_inaccurate'], 0)

    def test_matching_uses_highest_confidence_qualifying_board(self):
        records = self.records()
        row = records[0]
        row['boxes'] = np.array([[0, 0, 98, 98], [0, 0, 99, 99]])
        row['scores'] = np.array([.8, .01])
        row['points'] = np.concatenate([row['points'], row['points'] + [5, 0, 0]])
        result = summarize(records, ['a', 'b', 'c', 'd'], .5, .7, .01)
        self.assertEqual(result['per_landmark']['a']['mean_px'], 0)
