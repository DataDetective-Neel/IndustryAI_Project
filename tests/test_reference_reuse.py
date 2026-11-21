import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from pcb_landmarks.web import create_app


def board(seed=5):
    rng = np.random.default_rng(seed)
    image = np.full((480, 600, 3), 12, np.uint8)
    image[35:445, 45:555] = (25, 110, 55)
    for i in range(160):
        x, y = rng.integers([65, 55], [535, 425])
        color = tuple(int(v) for v in rng.integers(90, 240, 3))
        cv2.rectangle(image, (x-5, y-4), (x+8, y+6), color, -1)
        cv2.putText(image, str(i), (x, y), cv2.FONT_HERSHEY_SIMPLEX, .3, (230, 220, 170), 1)
    # Shared textured background must not supply alignment evidence.
    for y in range(8, 480, 23):
        cv2.putText(image, 'SAME BACKGROUND', (0, y), cv2.FONT_HERSHEY_SIMPLEX, .4, (180, 180, 180), 1)
    return image


class ReferenceReuseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.client = TestClient(create_app(Path(self.folder.name)))
        self.reference = board()
        self.points = [[160, 130], [440, 130], [440, 350], [160, 350]]
        self.polygon = [[45, 35], [554, 35], [554, 444], [45, 444]]

    def upload(self, image):
        stream = io.BytesIO()
        Image.fromarray(image).save(stream, format='PNG')
        return self.client.post('/api/photos', files={'image': ('board.png', stream.getvalue(), 'image/png')}).json()['id']

    def setup_reference(self):
        self.ref = self.upload(self.reference)
        response = self.client.post(f'/api/references/{self.ref}', json=dict(points=self.points, board_polygon=self.polygon))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def inspect(self, images):
        response = self.client.post('/api/inspections', json=dict(reference_id=self.ref,
            inspections=[dict(photo_id=self.upload(image)) for image in images],
            components=[dict(id='part', name='part', bbox_xyxy_px=[180, 180, 220, 220])], mode='automatic'))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['photos']

    def test_failed_yolo_reuses_reference_for_multiple_views_and_perspective(self):
        self.setup_reference()
        forward = np.array([[.85, .08, 25], [-.04, .88, 30], [.00008, -.0001, 1.]])
        tilted = cv2.warpPerspective(self.reference, forward, (600, 480))
        with patch('pcb_landmarks.web._detector', side_effect=ValueError('YOLO unavailable')):
            results = self.inspect([self.reference, tilted])
        for result, matrix in zip(results, [np.eye(3), forward]):
            self.assertTrue(result['components_evaluated'], result)
            self.assertEqual(result['alignment']['source'], 'reference_registration')
            actual = np.array(result['alignment']['inspection_points'])
            expected = cv2.perspectiveTransform(np.float64([self.points]), matrix)[0]
            self.assertLess(np.linalg.norm(actual-expected, axis=1).max(), 3)
        saved = self.client.get(f'/api/references/{self.ref}').json()
        self.assertEqual(saved['points'], self.points)
        new = self.upload(board(17))
        self.assertEqual(self.client.get(f'/api/references/{new}').json()['points'], [])

    def test_background_and_outline_alone_never_pass(self):
        self.setup_reference()
        wrong = board(19)
        blank = np.full_like(wrong, 120)
        with patch('pcb_landmarks.web._detector', side_effect=ValueError('YOLO unavailable')):
            for result in self.inspect([wrong, blank]):
                self.assertFalse(result['components_evaluated'])
                self.assertEqual(result['outcome'], 'review')
                self.assertEqual(result['alignment']['status'], 'failure')
                self.assertTrue(result['alignment']['reason'])

    def test_misplaced_yolo_candidate_falls_back_to_registration(self):
        self.setup_reference()
        from types import SimpleNamespace
        detector = SimpleNamespace(predict=lambda *args: dict(status='ok', reason=None,
            landmarks=[dict(x=x+30, y=y+20) for x, y in self.points]))
        with patch('pcb_landmarks.web._detector', return_value=(detector, dict(board_conf=.75, point_conf=.85))):
            result = self.inspect([self.reference])[0]
        self.assertTrue(result['components_evaluated'], result)
        self.assertEqual(result['alignment']['source'], 'reference_registration')
        self.assertEqual(result['alignment']['attempts'][0]['source'], 'yolo_landmarks')
        self.assertEqual(result['alignment']['attempts'][0]['status'], 'failure')

    def test_reference_validation_and_changed_setup(self):
        self.setup_reference()
        for points in [[[1, 1]]*4, [[-1, 0], *self.points[1:]]]:
            response = self.client.post(f'/api/references/{self.ref}', json=dict(points=points, board_polygon=self.polygon))
            self.assertEqual(response.status_code, 422)
        response = self.client.post(f'/api/references/{self.ref}', json=dict(points=self.points,
            board_polygon=[[80, 60], [520, 60], [520, 420], [80, 420]]))
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.json()['board_polygon'], self.polygon)

    def test_valid_yolo_candidate_is_independently_verified(self):
        self.setup_reference()
        from types import SimpleNamespace
        detector = SimpleNamespace(predict=lambda *args: dict(status='ok', reason=None,
            landmarks=[dict(x=x, y=y) for x, y in self.points]))
        with patch('pcb_landmarks.web._detector', return_value=(detector, dict(board_conf=.75, point_conf=.85))):
            result = self.inspect([self.reference])[0]
        self.assertTrue(result['components_evaluated'], result)
        self.assertEqual(result['alignment']['source'], 'yolo_landmarks')
        self.assertGreater(result['alignment']['verification']['held_out_inliers'], 8)

    def test_features_cached_per_reference_and_recomputed_on_replacement(self):
        from pcb_landmarks.registration import reference_features
        with patch('pcb_landmarks.web.reference_features', wraps=reference_features) as extract:
            self.setup_reference()
            with patch('pcb_landmarks.web._detector', side_effect=ValueError('YOLO unavailable')):
                self.inspect([self.reference, self.reference])
            self.assertEqual(extract.call_count, 1)
            self.setup_reference()
            self.assertEqual(extract.call_count, 2)


class IndependentDesignTests(unittest.TestCase):
    """Designs F/K belong to the pre-existing test split, outside the layout catalog."""
    setUp = ReferenceReuseTests.setUp
    upload = ReferenceReuseTests.upload
    setup_reference = ReferenceReuseTests.setup_reference
    inspect = ReferenceReuseTests.inspect

    def test_held_out_designs_with_failed_yolo(self):
        from pcb_landmarks.data import read_image
        from pcb_landmarks.registration import board_polygon
        for design in ['F', 'K']:
            with self.subTest(design=design):
                path = Path(f'PCB_Dataset_Pilot/images/test/{design}CCC5.jpg')
                if not path.is_file():
                    self.skipTest('Independent source photographs are not installed')
                self.reference = np.asarray(read_image(path))
                self.polygon = board_polygon(self.reference)
                # Interior, clockwise details; independent of the detected board boundary.
                self.points = [[400, 550], [900, 550], [900, 1100], [400, 1100]]
                self.setup_reference()
                images = [np.asarray(read_image(f'PCB_Dataset_Pilot/images/test/{design}{view}5.jpg'))
                          for view in ['BCC', 'CCB', 'DCC']]
                with patch('pcb_landmarks.web._detector', side_effect=ValueError('YOLO unavailable')):
                    results = self.inspect(images)
                for view, result in zip(['BCC', 'CCB', 'DCC'], results):
                    # F's strong tilt has visible parallax and must safely request review.
                    if design == 'F' and view == 'CCB':
                        self.assertFalse(result['components_evaluated'], result)
                        self.assertIn('Stable PCB details disagree', result['alignment']['reason'])
                    else:
                        self.assertTrue(result['components_evaluated'], result)
                        self.assertEqual(result['alignment']['source'], 'reference_registration')
                other = 'K' if design == 'F' else 'F'
                with patch('pcb_landmarks.web._detector', side_effect=ValueError('YOLO unavailable')):
                    result = self.inspect([np.asarray(read_image(f'PCB_Dataset_Pilot/images/test/{other}CCC5.jpg'))])[0]
                self.assertFalse(result['components_evaluated'], result)

    def test_generated_pair_regression(self):
        from pcb_landmarks.data import read_image
        from pcb_landmarks.registration import board_polygon
        paths = sorted(Path('A:/Downloads').glob('WhatsApp Image 2026-11-21 at 6.09.33 PM*.jpeg'))
        if len(paths) != 2:
            self.skipTest('User supplied generated pair is not installed')
        self.reference = np.asarray(read_image(paths[0]))
        self.polygon = board_polygon(self.reference)
        self.points = [[140, 135], [1120, 135], [1120, 1135], [140, 1135]]
        self.setup_reference()
        with patch('pcb_landmarks.web._detector', side_effect=ValueError('YOLO unavailable')):
            result = self.inspect([np.asarray(read_image(paths[1]))])[0]
        self.assertTrue(result['components_evaluated'], result)
        self.assertEqual(result['alignment']['source'], 'reference_registration')
