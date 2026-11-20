import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from alignment_fixture import perspective_pair, save_pair
from pcb_landmarks.align import align_images, blend_overlay, label_points


class AlignmentTests(unittest.TestCase):
    def test_perspective_at_independent_controls_and_pixels(self):
        reference, inspection, rp, ip, forward, controls = perspective_pair()
        aligned, homography, mask = align_images(reference, inspection, rp, ip)
        projected = cv2.perspectiveTransform(controls[None], forward)
        recovered = cv2.perspectiveTransform(projected, homography)[0]
        self.assertLess(np.linalg.norm(recovered - controls, axis=1).max(), .001)
        self.assertEqual(aligned.shape, reference.shape)
        self.assertEqual(mask.dtype, np.uint8)
        self.assertEqual(set(np.unique(mask)), {0, 255})
        interior = cv2.erode(mask, np.ones((5, 5), np.uint8)) > 0
        self.assertLess(np.abs(aligned.astype(float) - reference)[interior].mean(), 8)
        # The known forward transform, not the fitted H, defines source coverage.
        yy, xx = np.indices(mask.shape)
        source = cv2.perspectiveTransform(np.stack((xx, yy), axis=-1).astype(float), forward)
        outside = ((source[:, :, 0] < -1e-5) | (source[:, :, 0] > inspection.shape[1]-1+1e-5) |
                   (source[:, :, 1] < -1e-5) | (source[:, :, 1] > inspection.shape[0]-1+1e-5))
        self.assertTrue(outside.any())
        self.assertTrue((mask[outside] == 0).all())
        self.assertTrue((mask[70:180, 70:230] == 255).all())

    def test_subpixel_border_is_not_valid_and_overlay_marks_it(self):
        image = np.full((100, 100, 3), 100, np.uint8)
        points = np.array([[10, 10], [80, 10], [80, 80], [10, 80]], dtype=float)
        aligned, _, mask = align_images(image, image, points + [.5, 0], points)
        self.assertTrue((mask[:, 0] == 0).all())
        self.assertTrue((mask[:, 1:] == 255).all())
        aligned[50, 50] = [20, 40, 60]
        overlay = blend_overlay(image, aligned, mask)
        np.testing.assert_array_equal(overlay[50, 50], [60, 70, 80])
        self.assertFalse(np.array_equal(overlay[50, 0], image[50, 0]))
        # OpenCV rounds interpolation coordinates; even a 0.01px exterior is invalid.
        _, _, mask = align_images(image, image, points + [.01, 0], points)
        self.assertTrue((mask[:, 0] == 0).all())

    def test_rotation_preserves_identities(self):
        reference, _, points, _, _, _ = perspective_pair()
        inspection = np.rot90(reference, 2).copy()
        rotated = [reference.shape[1]-1, reference.shape[0]-1] - points
        aligned, _, mask = align_images(reference, inspection, points, rotated)
        np.testing.assert_array_equal(aligned, reference)
        self.assertTrue((mask == 255).all())

    def test_bad_geometry_and_images_rejected(self):
        image = np.zeros((100, 100, 3), np.uint8)
        points = np.array([[10, 10], [80, 10], [80, 80], [10, 80]], dtype=float)
        bad_cases = [points[:3], np.ones((4, 3)), points * np.nan, points * np.inf,
                     points - 20, points + 20, np.tile(points[0], (4, 1)),
                     [[10, 10], [10.1, 10], [80, 80], [10, 80]],
                     [[10, 10], [40, 10], [80, 10.001], [10, 80]],
                     points[[0, 2, 1, 3]], points[[0, 3, 2, 1]],
                     [[10, 10], [30, 10], [20, 20], [10, 80]]]
        for bad in bad_cases:
            for ref, ins in [(bad, points), (points, bad)]:
                with self.subTest(points=bad), self.assertRaises(ValueError):
                    align_images(image, image, ref, ins)
        for bad in [image[:0], image[:, :, 0], image.astype(float)]:
            with self.assertRaises(ValueError):
                align_images(bad, image, points, points)

    def test_horizon_crossing_image_rejected(self):
        image = np.zeros((200, 200, 3), np.uint8)
        points = np.array([[60, 30], [150, 30], [150, 120], [60, 120]], dtype=float)
        horizon = np.array([[.2, 0, -10], [0, .2, 0], [.01, 0, -.2]])
        destination = cv2.perspectiveTransform(points[None], horizon)[0]
        with self.assertRaisesRegex(ValueError, 'horizon'):
            align_images(image, image, destination, points)

    def test_cli_decoded_dimensions_outputs_and_rejections(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_pair(root / 'input')
            source = root / 'input'
            command = [sys.executable, '-m', 'pcb_landmarks.align',
                       '--reference', str(source / 'reference.png'),
                       '--inspection', str(source / 'inspection.png'),
                       '--reference-label', str(source / 'reference.txt'),
                       '--inspection-label', str(source / 'inspection.txt'),
                       '--output', str(root / 'result')]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            report = json.loads(run.stdout)
            self.assertEqual(report['status'], 'ok')
            self.assertEqual(report['reference_wh'], [320, 240])
            self.assertEqual(report['inspection_wh'], [300, 280])
            _, _, _, _, forward, controls = perspective_pair()
            recovered = cv2.perspectiveTransform(cv2.perspectiveTransform(controls[None], forward),
                np.array(report['homography_inspection_to_reference']))[0]
            self.assertLess(np.linalg.norm(recovered - controls, axis=1).max(), .001)
            for name in ['aligned.png', 'overlay.png', 'overlap_mask.png']:
                with Image.open(root / 'result' / name) as saved:
                    self.assertEqual(saved.size, (320, 240))
            self.assertEqual(json.loads((root / 'result/alignment.json').read_text()), report)
            np.testing.assert_allclose(label_points(source / 'reference.txt', (320, 240)),
                                       perspective_pair()[2], atol=1e-8)
            repeat = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(repeat.returncode, 2)
            self.assertEqual(json.loads(repeat.stdout)['status'], 'failure')
            label = source / 'inspection.txt'
            label.write_text(label.read_text().replace(' 2', ' 0', 1))
            command[-1] = str(root / 'invalid')
            rejected = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertIn('visible', json.loads(rejected.stdout)['reason'])
            self.assertFalse((root / 'invalid').exists())

    def test_cli_rejects_exif_rotation_and_missing_image(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_pair(root / 'input')
            image = Image.new('RGB', (320, 240))
            exif = image.getexif()
            exif[274] = 6
            image.save(root / 'rotated.jpg', exif=exif)
            for reference, reason in [(root / 'rotated.jpg', 'EXIF'), (root / 'missing.png', 'FileNotFoundError')]:
                run = subprocess.run([sys.executable, '-m', 'pcb_landmarks.align',
                    '--reference', str(reference), '--inspection', str(root / 'input/inspection.png'),
                    '--reference-label', str(root / 'input/reference.txt'),
                    '--inspection-label', str(root / 'input/inspection.txt'),
                    '--output', str(root / 'result')], capture_output=True, text=True)
                self.assertEqual(run.returncode, 2)
                self.assertIn(reason, json.loads(run.stdout)['reason'])
                self.assertFalse((root / 'result').exists())


if __name__ == '__main__':
    unittest.main()
