import unittest

from pcb_landmarks.component_detection import propose_components
from pcb_landmarks.data import read_image


class ComponentDetectionTests(unittest.TestCase):
    def test_real_golden_board_produces_bounded_unknown_candidates(self):
        image = read_image('PCB_Dataset_Pilot/images/val/ECCC5.jpg')
        result = propose_components(image)
        self.assertGreaterEqual(result['candidate_count'], 6)
        self.assertLessEqual(result['candidate_count'], 36)
        self.assertFalse(result['verified'])
        self.assertEqual(len({part['id'] for part in result['components']}), result['candidate_count'])
        for part in result['components']:
            x1, y1, x2, y2 = part['bbox_xyxy_px']
            self.assertTrue(0 <= x1 < x2 <= image.width and 0 <= y1 < y2 <= image.height)
            self.assertEqual(part['candidate_status'], 'UNKNOWN')

    def test_known_component_centers_receive_candidate_coverage(self):
        image = read_image('PCB_Dataset_Pilot/images/val/ECCC5.jpg')
        proposals = propose_components(image)['components']
        expected_centers = [(430, 490), (632, 828), (773, 598), (570, 527)]
        covered = 0
        for x, y in expected_centers:
            covered += any(x1 <= x <= x2 and y1 <= y <= y2
                           for x1, y1, x2, y2 in (part['bbox_xyxy_px'] for part in proposals))
        self.assertGreaterEqual(covered, 2)

    def test_small_or_invalid_image_fails_cleanly(self):
        from PIL import Image
        with self.assertRaisesRegex(ValueError, 'at least 80x80'):
            propose_components(Image.new('RGB', (40, 40)))


if __name__ == '__main__':
    unittest.main()
