"""Synthetic geometry checks, not independent PCB accuracy evaluation."""
import unittest

import numpy as np

from pcb_landmarks.correspondence import assign_components, transform_components


def part(identifier, box, cls=None):
    return dict(id=identifier, bbox_xyxy_px=box, proposal_confidence=.9,
                proposal_evidence=dict(class_id=cls))


class CorrespondenceTests(unittest.TestCase):
    def test_one_detection_cannot_match_two_reference_parts(self):
        reference = [part('a', [20, 20, 40, 40]), part('b', [42, 20, 62, 40])]
        matches = assign_components(reference, [part('observed', [25, 20, 45, 40])])
        self.assertEqual(set(matches), {'a'})
        self.assertEqual(matches['a']['observed_id'], 'observed')

    def test_class_size_and_distance_gate_unrelated_detections(self):
        reference = [part('a', [20, 20, 40, 40], 1)]
        for observed in [part('wrong-class', [20, 20, 40, 40], 2),
                         part('remote', [100, 100, 120, 120], 1),
                         part('oversized', [0, 0, 80, 80], 1)]:
            self.assertEqual(assign_components(reference, [observed]), {})

    def test_assignment_preserves_local_order_for_identical_neighbors(self):
        reference = [part('a', [20, 20, 40, 40]), part('b', [45, 20, 65, 40])]
        observed = [part('second', [48, 20, 68, 40]), part('first', [23, 20, 43, 40])]
        matches = assign_components(reference, observed)
        self.assertEqual([matches[p]['observed_id'] for p in ['a', 'b']], ['first', 'second'])
        self.assertAlmostEqual(matches['a']['displacement_px'], 3)

    def test_transform_all_four_box_corners_into_reference_coordinates(self):
        source = [part('x', [10, 20, 30, 40], 1)]
        result = transform_components(source, np.array([[0, -1, 100], [1, 0, 0], [0, 0, 1.]]), (100, 100))
        self.assertEqual(result[0]['bbox_xyxy_px'], [60, 10, 80, 30])
        self.assertEqual(result[0]['original_bbox_xyxy_px'], source[0]['bbox_xyxy_px'])
        self.assertEqual(source[0]['bbox_xyxy_px'], [10, 20, 30, 40])

    def test_appearance_breaks_an_ambiguous_spatial_tie(self):
        rng = np.random.default_rng(3)
        reference = rng.integers(0, 255, (100, 100, 3), dtype=np.uint8)
        inspection = reference.copy()
        inspection[20:40, 36:56] = reference[20:40, 20:40]
        matches = assign_components([part('a', [20, 20, 40, 40])],
            [part('false', [4, 20, 24, 40]), part('true', [36, 20, 56, 40])], reference, inspection)
        self.assertEqual(matches['a']['observed_id'], 'true')
