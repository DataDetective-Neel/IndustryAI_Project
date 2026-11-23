import json
import unittest
from pathlib import Path

import pcb_landmarks.component_detection as component_detection
from pcb_landmarks.component_detection import _box_iou, propose_components
from pcb_landmarks.data import read_image


class ComponentDetectionTests(unittest.TestCase):
    def test_real_golden_board_produces_bounded_unknown_candidates(self):
        image = read_image('PCB_Dataset_Pilot/images/val/ECCC5.jpg')
        result = propose_components(image)
        self.assertGreaterEqual(result['candidate_count'], 6)
        self.assertLessEqual(result['candidate_count'], 1000)
        self.assertFalse(result['verified'])
        self.assertEqual(len({part['id'] for part in result['components']}), result['candidate_count'])
        for part in result['components']:
            x1, y1, x2, y2 = part['bbox_xyxy_px']
            self.assertEqual(part['center_xy_px'], [(x1+x2)/2, (y1+y2)/2])
            self.assertEqual(part['width_px'], x2-x1)
            self.assertEqual(part['height_px'], y2-y1)
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

    def test_reference_map_seeds_all_annotated_components_at_iou_half(self):
        image = read_image('PCB_Dataset_Pilot/images/val/ECCC5.jpg')
        annotated = json.loads(Path('configs/components-ECCC5.json').read_text(encoding='utf-8'))
        proposals = propose_components(image, reference_components=annotated['components'])['components']
        matched = sum(max(_box_iou(expected['bbox_xyxy_px'], proposal['bbox_xyxy_px'])
                          for proposal in proposals) >= .5
                      for expected in annotated['components'])
        self.assertEqual(matched, len(annotated['components']))
        self.assertTrue(all(part['candidate_status'] == 'UNKNOWN' for part in proposals))

    def test_antigravity_map_validates_identity_dimensions_and_xywh_coordinates(self):
        self.assertTrue(hasattr(component_detection, 'import_component_map'))
        import_component_map = component_detection.import_component_map
        mapping = {
            'metadata': {
                'reference_image_id': 'golden_reference.png',
                'image_dimensions': {'width': 969, 'height': 1024, 'channels': 3},
            },
            'components': [{
                'id': 'U1', 'description': 'Main controller', 'bbox': [390, 442, 230, 230],
            }],
        }
        components = import_component_map(mapping, (969, 1024), 'golden_reference.png')
        self.assertEqual(components[0]['bbox_xyxy_px'], [390, 442, 620, 672])
        self.assertEqual(components[0]['name'], 'U1 — Main controller')
        with self.assertRaisesRegex(ValueError, 'dimensions'):
            import_component_map(mapping, (970, 1024), 'golden_reference.png')
        with self.assertRaisesRegex(ValueError, 'reference image'):
            import_component_map(mapping, (969, 1024), 'another.png')

    def test_small_or_invalid_image_fails_cleanly(self):
        from PIL import Image
        with self.assertRaisesRegex(ValueError, 'at least 80x80'):
            propose_components(Image.new('RGB', (40, 40)))


if __name__ == '__main__':
    unittest.main()
