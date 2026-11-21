import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from pcb_landmarks.align import label_points
from pcb_landmarks.data import read_image
from pcb_landmarks.web import create_app
from pcb_landmarks.compatibility import CATALOG, _profiles


class BoardCompatibilityTests(unittest.TestCase):
    def test_stable_template_features_are_inside_board_boundaries(self):
        for profile in _profiles(str(CATALOG)):
            polygon = np.float32(profile['board_polygon'])
            for point in profile['keypoints']:
                location = tuple(np.array(point.pt)/profile['scale'])
                self.assertGreaterEqual(cv2.pointPolygonTest(polygon, location, False), 0)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.client = TestClient(create_app(Path(self.folder.name)))

    def photo(self, name):
        image = read_image(f'PCB_Dataset_Pilot/images/train/{name}.jpg')
        points = label_points(f'PCB_Dataset_Pilot/labels/train/{name}.txt', image.size)
        return np.asarray(image), points

    def upload(self, array):
        data = io.BytesIO()
        Image.fromarray(array).save(data, format='PNG')
        response = self.client.post('/api/photos', files={'image': ('renamed.png', data.getvalue(), 'image/png')})
        self.assertEqual(response.status_code, 200)
        return response.json()['id']

    def inspect(self, reference, inspection, rp, ip, mode='manual', synthetic=False):
        response = self.client.post('/api/inspections', json=dict(
            reference_id=self.upload(reference), reference_points=rp.tolist(),
            inspections=[dict(photo_id=self.upload(inspection), points=ip.tolist())],
            components=[dict(id='processor', name='Main processor', bbox_xyxy_px=[390, 705, 620, 935])],
            mode=mode, synthetic=synthetic))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['photos'][0]

    def test_wrong_board_has_positive_layout_evidence_and_skips_components(self):
        reference, rp = self.photo('ACCC5')
        inspection, ip = self.photo('MBCC5')
        for mode in ['manual', 'automatic']:
            with self.subTest(mode=mode), patch('pcb_landmarks.web.compare_regions') as compare, \
                 patch('pcb_landmarks.web._detector') as detector:
                result = self.inspect(reference, inspection, rp, ip, mode)
                self.assertEqual(result['outcome'], 'DIFFERENT_BOARD')
                self.assertEqual(result['reason'], 'Inspection board does not match the reference design.')
                self.assertEqual(result['components'], [])
                self.assertFalse(result['components_evaluated'])
                self.assertGreaterEqual(len(result['board_compatibility']['reference']['matched_regions']), 3)
                self.assertGreaterEqual(len(result['board_compatibility']['inspection']['matched_regions']), 3)
                compare.assert_not_called()
                detector.assert_not_called()

    def test_blue_board_angle_controls_reach_component_inspection(self):
        reference, rp = self.photo('ACCC5')
        for name in ['ACCC5', 'ABCC5', 'ACCB5', 'ACDC5', 'ADCC5']:
            with self.subTest(image=name):
                inspection, ip = self.photo(name)
                result = self.inspect(reference, inspection, rp, ip)
                self.assertEqual(result['board_compatibility']['status'], 'SAME_DESIGN')
                self.assertTrue(result['components_evaluated'])
                self.assertEqual(result['components'][0]['status'], 'present')

    def test_localized_simulated_absence_is_not_a_different_board(self):
        reference, rp = self.photo('ACCC5')
        inspection = reference.copy()
        inspection[705:935, 390:620] = (25, 65, 85)
        result = self.inspect(reference, inspection, rp, rp, synthetic=True)
        self.assertEqual(result['board_compatibility']['status'], 'SAME_DESIGN')
        self.assertTrue(result['components_evaluated'])
        self.assertEqual(result['components'][0]['status'], 'uncertain')

    def test_existing_beaglebone_angle_pair_keeps_component_review(self):
        reference = read_image('PCB_Dataset_Pilot/images/val/ECCC5.jpg')
        inspection = read_image('PCB_Dataset_Pilot/images/val/ECCB5.jpg')
        rp = label_points('PCB_Dataset_Pilot/labels/val/ECCC5.txt', reference.size)
        ip = label_points('PCB_Dataset_Pilot/labels/val/ECCB5.txt', inspection.size)
        result = self.inspect(np.asarray(reference), np.asarray(inspection), rp, ip)
        self.assertEqual(result['board_compatibility']['status'], 'SAME_DESIGN')
        self.assertTrue(result['components_evaluated'])

    def test_blur_crop_unknown_layout_and_bad_alignment_are_review(self):
        reference, rp = self.photo('ACCC5')
        wrong, wrong_points = self.photo('MBCC5')
        angle, angle_points = self.photo('ACDC5')
        cases = [
            (cv2.GaussianBlur(wrong, (81, 81), 20), wrong_points),
            (wrong[:, wrong.shape[1]//2:], wrong_points-[wrong.shape[1]//2, 0]),
            (np.random.default_rng(3).integers(0, 255, reference.shape, dtype=np.uint8), rp),
            (angle, angle_points+[50, 40]),
        ]
        for index, (image, points) in enumerate(cases):
            with self.subTest(case=index), patch('pcb_landmarks.web.compare_regions') as compare:
                result = self.inspect(reference, image, rp, points)
                self.assertEqual(result['outcome'], 'review')
                self.assertFalse(result['components_evaluated'])
                compare.assert_not_called()
