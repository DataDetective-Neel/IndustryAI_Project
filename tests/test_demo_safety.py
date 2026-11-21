import unittest
from unittest.mock import Mock
import cv2
import numpy as np
from pcb_landmarks.compare import compare_regions
from pcb_landmarks.infer import LandmarkDetector
from PIL import Image

class DemoSafetyTests(unittest.TestCase):
    def setUp(self):
        self.ref = np.random.default_rng(7).integers(0, 255, (160, 200, 3), dtype=np.uint8)
        self.regions = dict(reference_wh_px=[200,160], components=[dict(id=str(i),name=str(i),bbox_xyxy_px=b) for i,b in enumerate([[30,30,60,60],[90,30,120,60],[30,90,60,120]])])
    def compare(self, image):
        return compare_regions(self.ref,image,np.full((160,200),255,np.uint8),self.regions,dict(missing_max=.25,present_min=.5),dict(status='ok',reference_wh=[200,160]))
    def test_low_similarity_alone_never_means_missing(self):
        result=self.compare(np.random.default_rng(8).integers(0,255,self.ref.shape,dtype=np.uint8))
        self.assertEqual(result['outcome'],'review')
        self.assertNotIn('missing',[p['status'] for p in result['components']])
    def test_bounded_search_recovers_small_shift(self):
        image=cv2.warpAffine(self.ref,np.float32([[1,0,2],[0,1,-2]]),(200,160))
        result=self.compare(image)
        self.assertTrue(all(p['status']=='present' for p in result['components']))
        self.assertEqual(result['components'][0]['best_match_offset_px'],[2,-2])
    def test_shift_outside_search_cannot_match_a_neighbor(self):
        image=cv2.warpAffine(self.ref,np.float32([[1,0,12],[0,1,0]]),(200,160))
        result=self.compare(image)
        self.assertEqual(result['outcome'],'review')
        self.assertTrue(all(p['status']=='uncertain' for p in result['components']))
    def test_zero_overlay_and_no_matches_requires_review(self):
        result=self.compare(np.zeros_like(self.ref))
        self.assertEqual(result['outcome'],'review')
        self.assertFalse(result['alignment_validation']['reliable'])
        self.assertTrue(all(p['status']=='uncertain' for p in result['components']))
    def test_clipped_expected_box_is_review_before_scoring(self):
        mask=np.full((160,200),255,np.uint8);mask[30,30]=0
        result=compare_regions(self.ref,self.ref,mask,self.regions,dict(missing_max=.25,present_min=.5),dict(status='ok',reference_wh=[200,160]))
        self.assertEqual(result['components'][0]['status'],'uncertain')
        self.assertIsNone(result['components'][0]['score'])
        self.assertIn('coverage',result['components'][0]['reason'])
    def test_detector_retains_below_threshold_raw_evidence(self):
        d=LandmarkDetector.__new__(LandmarkDetector)
        d.names=['a','b','c','d']; d.sha256='test'; d.checkpoint='test.pt';d.imgsz=640
        d.raw=Mock(return_value=(np.array([[0,0,99,99]]),np.array([.9]),np.array([[[10,10,.1],[80,10,.8],[80,90,.9],[10,90,.9]]])))
        result=d.predict(Image.new('RGB',(100,100)),.95,.99)
        self.assertEqual(result['reason'],'no_confident_board')
        self.assertEqual(result['diagnostics']['candidates'][0]['landmarks'][0]['confidence'],.1)
        self.assertLessEqual(d.raw.call_args.args[1],.001)
