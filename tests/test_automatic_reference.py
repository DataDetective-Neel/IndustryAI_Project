import unittest
from unittest.mock import patch

import test_reference_reuse as fixtures


class AutomaticReferenceTests(unittest.TestCase):
    setUp = fixtures.ReferenceReuseTests.setUp
    upload = fixtures.ReferenceReuseTests.upload
    inspect = fixtures.ReferenceReuseTests.inspect

    def test_automatic_setup_is_ordered_persisted_and_reusable(self):
        self.ref = self.upload(self.reference)
        response = self.client.post(f'/api/references/{self.ref}/automatic')
        self.assertEqual(response.status_code, 200, response.text)
        setup = response.json()
        self.assertTrue(setup['confirmed'])
        self.assertEqual(len(setup['points']), 4)
        self.assertGreater(setup['feature_count'], 35)
        self.assertEqual(self.client.get(f'/api/references/{self.ref}').json(), setup)
        with patch('pcb_landmarks.web._detector', side_effect=ValueError('YOLO unavailable')):
            result = self.inspect([self.reference])[0]
        self.assertTrue(result['components_evaluated'], result)
        self.assertEqual(result['alignment']['status'], 'ok')
        self.assertFalse(any(p['status'] == 'missing' for p in result['components']))

    def test_manual_correction_is_not_overwritten_by_automatic_setup(self):
        self.ref = self.upload(self.reference)
        saved = self.client.post(f'/api/references/{self.ref}', json=dict(
            points=self.points, board_polygon=self.polygon)).json()
        self.assertEqual(self.client.post(f'/api/references/{self.ref}/automatic').json(), saved)

    def test_reliable_distributed_yolo_mounts_are_preferred(self):
        from types import SimpleNamespace
        detector = SimpleNamespace(predict=lambda *args: dict(status='ok', reason=None,
            landmarks=[dict(x=x, y=y) for x,y in self.points]))
        self.ref = self.upload(self.reference)
        with patch('pcb_landmarks.web._detector', return_value=(detector, dict(board_conf=.75, point_conf=.85))):
            setup = self.client.post(f'/api/references/{self.ref}/automatic').json()
            result = self.inspect([self.reference])[0]
        self.assertEqual(setup['points'], self.points)
        self.assertEqual(setup['source'], 'yolo_landmarks')
        self.assertEqual(result['alignment']['source'], 'yolo_landmarks')
