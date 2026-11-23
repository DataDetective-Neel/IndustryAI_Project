import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

import test_reference_reuse as fixtures
from pcb_landmarks.compatibility import check_compatibility
from pcb_landmarks.component_detection import import_component_map
from pcb_landmarks.data import read_image
from pcb_landmarks.registration import automatic_reference, reference_features, register_inspection


class LandmarkScoringRegressionTests(unittest.TestCase):
    setUp = fixtures.ReferenceReuseTests.setUp
    upload = fixtures.ReferenceReuseTests.upload

    def golden(self):
        root=Path(os.environ.get('PCB_REPAIR_DATASET','A:/IndustryAI_Dataset_Worktree/dataset_generation'))
        if not (root/'golden/golden_reference.png').is_file():
            self.skipTest('ELEGOO evaluation source is not installed')
        image=read_image(root/'golden/golden_reference.png')
        parts=import_component_map(json.loads((root/'golden/golden_components.json').read_text()),image.size,'golden_reference.png')
        return root,image,parts

    def test_actual_models_run_and_project_physical_centers_after_pose_rejection(self):
        root,reference,parts=self.golden()
        setup=automatic_reference(reference)
        self.assertEqual(setup['landmark_kind'],'mounting_holes')
        ref=self.upload(np.asarray(reference))
        saved=self.client.post(f'/api/references/{ref}/automatic').json()
        self.assertTrue(saved['model_detection']['model_inference_ran'])
        other=self.upload(np.asarray(read_image(root/'images/misaligned/misaligned_002.png')))
        result=self.client.post('/api/inspections',json=dict(reference_id=ref,mode='automatic',components=parts,
            inspections=[dict(photo_id=other)])).json()['photos'][0]
        self.assertTrue(result['landmark_diagnostics']['inspection']['model_inference_ran'])
        self.assertEqual(result['alignment']['verification_status'],'verified')
        self.assertEqual(result['alignment']['landmark_kind'],'projected')
        self.assertEqual(len(result['alignment']['inspection_points']),4)
        matrix=np.asarray(result['alignment']['homography_inspection_to_reference'])
        recovered=cv2.perspectiveTransform(np.float64([result['alignment']['inspection_points']]),matrix)[0]
        np.testing.assert_allclose(recovered,saved['points'],atol=.01)
        self.assertEqual(result['component_inspection']['status'],'completed')
        self.assertEqual(result['component_inspection']['decision_count'],len(parts))
        self.assertEqual(result['component_detection_evidence']['inspection']['status'],'ok')

    def test_manual_missing_board_recovers_from_false_appearance_review(self):
        root,reference,parts=self.golden()
        setup=automatic_reference(reference)
        features=reference_features(reference,setup['board_polygon'])
        missing=read_image(root/'images/missing/missing_001.png')
        aligned,_,mask,_=register_inspection(reference,missing,setup['points'],features,dict(status='failure',reason='test'))
        blurred=cv2.GaussianBlur(aligned,(9,9),1.8)
        unknown=dict(status='UNKNOWN')
        old=check_compatibility(unknown,unknown,reference,blurred,mask,np.eye(3),setup['points'])
        self.assertEqual(old['status'],'REVIEW')  # Reproduces the actual old gate.
        ref=self.upload(np.asarray(reference)); current=self.upload(blurred)
        with patch('pcb_landmarks.web.identify_board',return_value=unknown):
            result=self.client.post('/api/inspections',json=dict(reference_id=ref,mode='manual',
                reference_points=setup['points'],inspections=[dict(photo_id=current,points=setup['points'])],components=parts)).json()['photos'][0]
        self.assertEqual(result['alignment']['verification_status'],'verified',result)
        self.assertEqual(result['board_compatibility']['status'],'SAME_DESIGN')
        self.assertTrue(result['components_evaluated'])
        self.assertEqual(result['component_inspection']['decision_count'],len(parts))
        self.assertEqual(result['board_compatibility']['previous_assessment']['status'],'REVIEW')
        self.assertEqual(next(p for p in result['components'] if p['id']=='U1')['status'],'missing')
        np.testing.assert_allclose(result['alignment']['inspection_points'],setup['points'])

    def test_invalid_manual_homography_never_reaches_scoring(self):
        ref=self.upload(self.reference)
        result=self.client.post('/api/inspections',json=dict(reference_id=ref,mode='manual',
            reference_points=self.points,inspections=[dict(photo_id=self.upload(self.reference),points=[self.points[0]]*4)],
            components=[dict(id='x',name='x',bbox_xyxy_px=[180,180,220,220])])).json()['photos'][0]
        self.assertEqual(result['alignment']['status'],'failure')
        self.assertFalse(result['components_evaluated'])
        self.assertEqual(result['component_inspection']['status'],'blocked')
