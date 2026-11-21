import unittest

import cv2
import numpy as np
from PIL import Image

from pcb_landmarks.infer import assess_mounts, refine_mounts, verify_mount_orientation


class MountRefinementTests(unittest.TestCase):
    def test_pattern_recovers_landmark_identities_after_half_turn(self):
        image = np.random.default_rng(11).integers(0, 255, (256, 256, 3), dtype=np.uint8)
        points = [[0, 0], [255, 0], [255, 255], [0, 255]]
        shift, details = verify_mount_orientation(image, image, points)
        self.assertEqual(shift, 0)
        shift, details = verify_mount_orientation(image, np.rot90(image, 2).copy(), points)
        self.assertEqual(shift, 2)
        self.assertEqual(details['status'], 'ok')
        other = np.random.default_rng(12).integers(0, 255, image.shape, dtype=np.uint8)
        self.assertIsNone(verify_mount_orientation(image, other, points)[0])

    def test_refines_nearby_ring_centers_without_reordering(self):
        image = np.full((400, 500, 3), (30, 110, 75), np.uint8)
        centers = np.array([[70, 70], [420, 65], [415, 330], [75, 335]], dtype=float)
        for x, y in centers.astype(int):
            cv2.circle(image, (x, y), 18, (165, 115, 35), -1)
            cv2.circle(image, (x, y), 10, (90, 90, 90), -1)
        points, details = refine_mounts(image, centers + [7, -5])
        np.testing.assert_allclose(points, centers, atol=1)
        self.assertEqual(details['status'], 'ok')

    def test_missing_ring_and_distant_proposals_require_review(self):
        image = np.full((400, 500, 3), (30, 110, 75), np.uint8)
        points, details = refine_mounts(image, [[70, 70], [420, 65], [415, 330], [75, 335]])
        self.assertIsNone(points)
        self.assertEqual(details['status'], 'failure')

    def test_duplicate_board_proposals_share_verified_holes_but_separate_boards_fail(self):
        image = np.full((400, 500, 3), (30, 110, 75), np.uint8)
        centers = np.array([[70, 70], [420, 65], [415, 330], [75, 335]], dtype=float)
        for x, y in centers.astype(int):
            cv2.circle(image, (x, y), 18, (165, 115, 35), -1)
            cv2.circle(image, (x, y), 10, (90, 90, 90), -1)
        keypoints = np.array([np.column_stack((centers, [.99]*4))]*2)
        # A higher box score must not beat a proposal with verified, confident landmarks.
        keypoints[0, 0, 2] = .3
        boxes = [[30, 30, 470, 370], [32, 32, 468, 368]]
        result = assess_mounts(Image.fromarray(image), boxes, [.99, .9], keypoints,
                               ['a', 'b', 'c', 'd'], .75, .85)
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['selected_board_id'], 1)
        boxes[0] = [0, 0, 150, 200]
        result = assess_mounts(Image.fromarray(image), boxes, [.99, .9], keypoints,
                               ['a', 'b', 'c', 'd'], .75, .85)
        self.assertEqual(result['reason'], 'ambiguous_boards')
        boxes[0] = [np.nan, 0, 150, 200]
        result = assess_mounts(Image.fromarray(image), boxes, [.99, .9], keypoints,
                               ['a', 'b', 'c', 'd'], .75, .85)
        self.assertEqual(result['reason'], 'nonfinite_prediction')

    def test_clipped_ring_and_far_proposals_are_not_invented(self):
        image = np.full((400, 500, 3), (30, 110, 75), np.uint8)
        centers = np.array([[70, 70], [420, 65], [415, 330], [75, 335]], dtype=float)
        for x, y in centers.astype(int):
            cv2.circle(image, (x, y), 18, (165, 115, 35), -1)
            cv2.circle(image, (x, y), 10, (90, 90, 90), -1)
        self.assertIsNone(refine_mounts(image, centers + [200, 200])[0])
        image[:110, :110] = (30, 110, 75)
        self.assertIsNone(refine_mounts(image, centers)[0])
