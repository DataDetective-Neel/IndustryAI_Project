import unittest
from unittest.mock import patch

from test_reference_reuse import ReferenceReuseTests


class AutomaticReferenceTests(unittest.TestCase):
    setUp = ReferenceReuseTests.setUp
    upload = ReferenceReuseTests.upload
    inspect = ReferenceReuseTests.inspect

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
