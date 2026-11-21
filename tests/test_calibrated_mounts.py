import unittest
import io
import json
import tempfile
from pathlib import Path

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from pcb_landmarks.align import label_points
from pcb_landmarks.compatibility import calibrated_mounts, identify_board
from pcb_landmarks.data import read_image
from pcb_landmarks.web import CHECKPOINT, _detector, create_app


class CalibratedMountTests(unittest.TestCase):
    def test_shared_pi_features_do_not_confuse_connector_layouts(self):
        detector, config = _detector(str(CHECKPOINT.resolve()))
        for name in ['MBCC5', 'MCCB5', 'MCDC5', 'MDCC5', 'HCCC5', 'HBCC5', 'HCCB5', 'HCDC5', 'HDCC5']:
            with self.subTest(image=name):
                image = read_image(f'PCB_Dataset_Pilot/images/train/{name}.jpg')
                layout = identify_board(image)
                self.assertEqual(layout['status'], 'IDENTIFIED')
                self.assertEqual(layout['layout_id'], 'micropcb_'+name[0])
                result = detector.predict(image, config['board_conf'], config['point_conf'])
                self.assertEqual(result['status'], 'ok', result['reason'])
                truth = label_points(f'PCB_Dataset_Pilot/labels/train/{name}.txt', image.size)
                points = np.array([[p['x'], p['y']] for p in result['landmarks']])
                self.assertLess(np.linalg.norm(points-truth, axis=1).max(), 8)

    def test_new_perspective_warp_preserves_holes_and_interior_feature_positions(self):
        matrix = np.array([[.98, .025, 14], [-.015, .97, 25], [.00001, -.000008, 1.]])
        for name in ['ACCC5', 'HCCC5']:
            with self.subTest(image=name):
                image = read_image(f'PCB_Dataset_Pilot/images/train/{name}.jpg')
                expected = label_points(f'PCB_Dataset_Pilot/labels/train/{name}.txt', image.size)
                warped = cv2.warpPerspective(np.asarray(image), matrix, image.size, borderValue=(180, 180, 180))
                points, evidence = calibrated_mounts(warped)
                self.assertEqual(evidence['status'], 'ok', evidence.get('reason'))
                truth = cv2.perspectiveTransform(expected[None], matrix)[0]
                self.assertLess(np.linalg.norm(points-truth, axis=1).max(), 4)
                interior = np.float64([[[400, 650], [600, 850], [700, 1100]]])
                recovered = cv2.perspectiveTransform(interior, np.array(evidence['layout']['template_to_image']))
                self.assertLess(np.linalg.norm(recovered-cv2.perspectiveTransform(interior, matrix), axis=2).max(), 4)

    def test_direct_and_uploaded_inference_agree_for_the_screenshot_layouts(self):
        detector, config = _detector(str(CHECKPOINT.resolve()))
        with tempfile.TemporaryDirectory() as folder:
            client = TestClient(create_app(Path(folder)))
            photos = {}
            for name in ['HCCC5', 'HBCC5', 'ACCC5', 'BCCC5', 'ACCB5', 'HCCB5']:
                with self.subTest(image=name):
                    image = read_image(f'PCB_Dataset_Pilot/images/train/{name}.jpg')
                    direct = detector.predict(image, config['board_conf'], config['point_conf'])
                    payload = io.BytesIO()
                    image.save(payload, format='PNG')
                    uploaded = client.post('/api/photos', files={'image': ('anonymous.png', payload.getvalue(), 'image/png')}).json()
                    photos[name] = uploaded['id']
                    response = client.post('/api/landmarks/'+uploaded['id'])
                    self.assertEqual(response.status_code, 200)
                    actual = response.json()
                    self.assertEqual(actual['status'], 'ok', actual.get('reason'))
                    self.assertEqual(actual['landmarks'], direct['landmarks'])
                    self.assertEqual(actual['source'], 'calibrated_layout_mounts')
                    self.assertTrue(all(not c['accepted'] for c in actual['diagnostics']['candidates']))
            for reference, inspections, box in [
                ('ACCC5', ['ACCB5'], [390, 705, 620, 935]),
                ('HCCC5', ['HBCC5', 'HCCB5'], [490, 950, 730, 1180]),
            ]:
                result = client.post('/api/inspections', json=dict(
                    reference_id=photos[reference], mode='automatic',
                    inspections=[dict(photo_id=photos[name]) for name in inspections],
                    components=[dict(id='processor', name='Processor', bbox_xyxy_px=box)]))
                self.assertEqual(result.status_code, 200, result.text)
                for photo in result.json()['photos']:
                    self.assertEqual(photo['board_compatibility']['status'], 'SAME_DESIGN')
                    self.assertTrue(photo['components_evaluated'])
                    self.assertFalse(any(c['status'] == 'missing' for c in photo['components']))

    def test_pictured_layouts_and_angles_have_four_local_verified_mounts(self):
        for family in ['A', 'B', 'H']:
            for view in ['CCC', 'BCC', 'CCB', 'CDC', 'DCC']:
                name = family+view+'5'
                with self.subTest(image=name):
                    image = read_image(f'PCB_Dataset_Pilot/images/train/{name}.jpg')
                    expected = label_points(f'PCB_Dataset_Pilot/labels/train/{name}.txt', image.size)
                    points, evidence = calibrated_mounts(image)
                    # Low-contrast black rims in these perspective views remain explicitly reviewable.
                    if name in ['BCCB5', 'BCDC5']:
                        self.assertIsNone(points)
                        self.assertEqual(evidence['reason'], 'local_mount_patch_not_verified')
                        continue
                    self.assertEqual(evidence['status'], 'ok', evidence)
                    self.assertEqual(evidence['layout_id'], 'micropcb_'+family)
                    self.assertLess(np.linalg.norm(points-expected, axis=1).max(), 8)

    def test_erased_mount_blur_and_crop_do_not_invent_points(self):
        image = read_image('PCB_Dataset_Pilot/images/train/HCCC5.jpg')
        points = label_points('PCB_Dataset_Pilot/labels/train/HCCC5.txt', image.size)
        erased = np.asarray(image).copy()
        x, y = np.round(points[0]).astype(int)
        erased[y-65:y+65, x-65:x+65] = (30, 90, 60)
        for bad in [erased, cv2.GaussianBlur(np.asarray(image), (81, 81), 20), np.asarray(image)[:, image.width//2:]]:
            with self.subTest(shape=bad.shape):
                actual, evidence = calibrated_mounts(bad)
                self.assertIsNone(actual)
                self.assertEqual(evidence['status'], 'failure')
                json.dumps(evidence, allow_nan=False)
