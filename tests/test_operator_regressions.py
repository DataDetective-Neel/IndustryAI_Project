"""Regressions from operator feedback; photograph-based generated fixtures."""
import os
import unittest
from unittest.mock import patch
from pathlib import Path

import numpy as np

from pcb_landmarks.data import read_image
from pcb_landmarks.registration import automatic_reference
import test_reference_reuse as fixtures


class OperatorLandmarkTests(unittest.TestCase):
    def test_reference_selects_the_outer_mounting_holes_not_an_internal_hole(self):
        root = Path(os.environ.get('PCB_REPAIR_DATASET', 'A:/IndustryAI_Dataset_Worktree/dataset_generation'))
        source = root/'golden/golden_reference.png'
        if not source.exists():
            self.skipTest('Operator photograph is not installed')
        setup = automatic_reference(read_image(source))
        # Visually checked centers in the original photograph; not production inputs.
        expected = [[188, 217], [756, 215], [759, 934], [188, 973]]
        self.assertEqual(setup['landmark_kind'], 'mounting_holes')
        np.testing.assert_allclose(setup['points'], expected, atol=4)

    def test_removed_capacitor_is_not_rescued_by_exposed_pad_edges(self):
        from pcb_landmarks.registration import reference_features, register_inspection
        from pcb_landmarks.compare import compare_regions, load_config
        root = Path(os.environ.get('PCB_REPAIR_DATASET', 'A:/IndustryAI_Dataset_Worktree/dataset_generation'))
        if not (root/'images/missing/missing_006.png').exists():
            self.skipTest('Operator fixture is not installed')
        reference = read_image(root/'golden/golden_reference.png')
        current = read_image(root/'images/missing/missing_006.png')
        setup = automatic_reference(reference)
        aligned, matrix, mask, registration = register_inspection(reference, current, setup['points'],
            reference_features(reference, setup['board_polygon']), dict(status='failure', reason='test fallback'))
        result = compare_regions(reference, aligned, mask,
            dict(reference_wh_px=list(reference.size), components=[dict(id='capacitor', name='Capacitor', bbox_xyxy_px=[226,211,314,287])]),
            load_config('configs/comparison.json'), dict(status='ok', reference_wh=list(reference.size),
                verification_status='verified', verification=registration['verification']))
        self.assertEqual(result['components'][0]['decision'], 'MISSING')


class InspectionPreviewTests(unittest.TestCase):
    setUp = fixtures.ReferenceReuseTests.setUp
    upload = fixtures.ReferenceReuseTests.upload
    setup_reference = fixtures.ReferenceReuseTests.setup_reference

    def test_preview_recovers_corresponding_points_when_pose_model_fails(self):
        self.setup_reference()
        current = self.upload(self.reference)
        with patch('pcb_landmarks.web._detector', side_effect=ValueError('Unavailable pose model')):
            response = self.client.post(f'/api/landmarks/{current}?reference_id={self.ref}')
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['source'], 'reference_registration')
        np.testing.assert_allclose([[p['x'], p['y']] for p in result['landmarks']], self.points, atol=.1)

    def test_manual_click_error_is_refined_without_discarding_original_clicks(self):
        self.setup_reference()
        clicks = (np.asarray(self.points)+[3,-2]).tolist()
        current = self.reference.copy()
        current[0,0] = (1,2,3)  # Different capture; bypass the identical-raster shortcut.
        response = self.client.post('/api/inspections', json=dict(reference_id=self.ref, mode='manual',
            reference_points=self.points, inspections=[dict(photo_id=self.upload(current), points=clicks)],
            components=[dict(id='part', name='Part', bbox_xyxy_px=[180,180,220,220])]))
        self.assertEqual(response.status_code, 200, response.text)
        alignment = response.json()['photos'][0]['alignment']
        self.assertEqual(alignment['source'], 'manual_landmarks_refined')
        self.assertEqual(alignment['manual_inspection_points'], clicks)
        np.testing.assert_allclose(alignment['inspection_points'], self.points, atol=.1)
        self.assertLess(alignment['verification']['p90_error_px'], .1)
