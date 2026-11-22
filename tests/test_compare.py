import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from comparison_fixture import comparison_pair, save_example
from pcb_landmarks.align import align_images
from pcb_landmarks.compare import compare_regions, load_config


class ComparisonTests(unittest.TestCase):
    def setUp(self):
        self.reference, inspection, rp, ip, self.regions = comparison_pair()
        self.aligned, _, self.mask = align_images(self.reference, inspection, rp, ip)
        self.config = load_config('configs/comparison.json')
        self.alignment = dict(status='ok', reference_wh=[320, 240])

    def compare(self, **changes):
        args = dict(reference=self.reference, aligned=self.aligned, mask=self.mask,
                    regions=self.regions, config=self.config, alignment=self.alignment)
        args.update(changes)
        return compare_regions(**args)

    def test_present_corroborated_synthetic_absence_and_coverage(self):
        result = self.compare()
        self.assertEqual(result['outcome'], 'defect')
        self.assertTrue(result['review_required'])
        parts = result['components']
        self.assertEqual([p['status'] for p in parts], ['present', 'missing', 'uncertain'])
        self.assertGreater(parts[0]['score'], .9)
        self.assertLess(parts[1]['score'], .25)
        self.assertLess(parts[1]['evidence']['edge_energy_ratio'], .45)
        self.assertLess(parts[2]['overlap'], 1)
        self.assertIsNone(parts[2]['score'])
        self.assertEqual(parts[2]['display_status'], 'Needs review')
        self.assertIn('coverage', parts[2]['reason'])

    def test_explicit_parallax_is_review_even_for_identical_crops(self):
        regions = copy.deepcopy(self.regions)
        regions['components'] = regions['components'][:1]
        regions['components'][0]['review_reason'] = 'visible connector parallax'
        result = self.compare(regions=regions, aligned=self.reference)
        self.assertEqual(result['outcome'], 'review')
        self.assertEqual(result['components'][0]['status'], 'uncertain')
        self.assertIsNone(result['components'][0]['score'])
        self.assertIn('parallax', result['components'][0]['reason'])

    def test_uninformative_crops_cannot_be_rescued_by_sharpening(self):
        for side in ['reference', 'aligned']:
            for sharpen in [False, True]:
                result = self.compare(**{side: np.full_like(self.reference, 80)}, sharpen=sharpen)
                for part in result['components'][:2]:
                    self.assertEqual(part['status'], 'uncertain')
                    self.assertIsNone(part['score'])
                    self.assertIn('texture', part['reason'])

    def test_threshold_boundaries_and_intermediate_review(self):
        score = self.compare()['components'][1]['score']
        for missing, present, expected in [(score, .9, 'missing'), (-.5, score, 'present'),
                                            (score-.1, score+.1, 'uncertain')]:
            config = dict(self.config, missing_max=missing, present_min=present)
            result = self.compare(config=config)
            self.assertEqual(result['components'][1]['status'], expected)

    def test_invalid_boxes_review_and_invalid_metadata_rejects(self):
        for box in [[-1, 0, 20, 20], [0, 0, 321, 20], [5, 5, 5, 20],
                    [1, 2, 3], [0, 0, 2, 2], [0, 0, 20.5, 20], [False, 0, 20, 20]]:
            regions = copy.deepcopy(self.regions)
            regions['components'][0]['bbox_xyxy_px'] = box
            result = self.compare(regions=regions)
            self.assertEqual(result['components'][0]['status'], 'uncertain')
            self.assertIsNone(result['components'][0]['score'])
        for change in [dict(components=[]), dict(reference_wh_px=[240, 320]),
                       dict(components=[self.regions['components'][0]]*2)]:
            with self.assertRaises(ValueError):
                self.compare(regions=dict(self.regions, **change))
        for mask in [self.mask[:-1], self.mask.astype(float), np.ones_like(self.mask)]:
            with self.assertRaises(ValueError):
                self.compare(mask=mask)
        with self.assertRaises(ValueError):
            self.compare(aligned=self.aligned[:, :-1])

    def test_failed_alignment_skips_classification(self):
        result = self.compare(aligned=None, mask=None,
                              alignment=dict(status='failure', reason='nearly collinear landmarks'))
        self.assertEqual(result['outcome'], 'review')
        self.assertTrue(result['review_required'])
        self.assertIn('collinear', result['reason'])
        self.assertTrue(all(p['status'] == 'not_evaluated' and p['score'] is None
                            for p in result['components']))

    def test_sharpening_changes_scores_but_not_fixture_decisions_or_inputs(self):
        before = self.aligned.copy()
        off, on = self.compare(), self.compare(sharpen=True)
        self.assertFalse(off['sharpening_enabled'])
        self.assertTrue(on['sharpening_enabled'])
        self.assertEqual([p['status'] for p in off['components']], [p['status'] for p in on['components']])
        self.assertNotEqual(off['components'][0]['score'], on['components'][0]['score'])
        np.testing.assert_array_equal(self.aligned, before)

    def test_configuration_rejects_unordered_or_nonfinite_thresholds(self):
        for config in [dict(self.config, missing_max=.9, present_min=.5),
                       dict(self.config, missing_max=float('nan')),
                       dict(self.config, present_min=2), dict(self.config, missing_max=True)]:
            with self.assertRaises(ValueError):
                self.compare(config=config)

    def test_all_present_with_symmetric_sharpening(self):
        regions = dict(self.regions, components=self.regions['components'][:2])
        for sharpen in [False, True]:
            result = self.compare(regions=regions, aligned=self.reference, sharpen=sharpen)
            self.assertEqual(result['outcome'], 'ok')
            self.assertFalse(result['review_required'])
            for part in result['components']:
                self.assertAlmostEqual(part['score'], 1, places=6)

    def test_constant_gradient_is_degenerate_despite_grayscale_texture(self):
        ramp = np.broadcast_to((np.arange(320) % 256)[None, :, None], self.reference.shape).astype(np.uint8)
        self.assertGreater(ramp[45:85, 60:100].std(), 2)
        for sharpen in [False, True]:
            result = self.compare(aligned=ramp, sharpen=sharpen)
            self.assertEqual(result['components'][0]['status'], 'uncertain')
            self.assertIn('texture', result['components'][0]['reason'])

    def test_cli_assets_and_failed_alignment_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            save_example(root / 'example')
            source = root / 'example/input'
            align = [sys.executable, '-m', 'pcb_landmarks.align', '--reference', str(source/'reference.png'),
                     '--inspection', str(source/'inspection.png'), '--reference-label', str(source/'reference.txt'),
                     '--inspection-label', str(source/'inspection.txt'), '--output', str(root/'aligned')]
            run = subprocess.run(align, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            command = [sys.executable, '-m', 'pcb_landmarks.compare', '--reference', str(source/'reference.png'),
                       '--aligned', str(root/'aligned/aligned.png'), '--mask', str(root/'aligned/overlap_mask.png'),
                       '--regions', str(root/'example/regions.json'), '--output', str(root/'result')]
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
            report = json.loads((root/'result/report.json').read_text())
            self.assertEqual(report['outcome'], 'defect')
            with Image.open(root/'result/overlay.png') as overlay:
                self.assertEqual(overlay.size, (320, 240))
            repeat = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(repeat.returncode, 2)
            self.assertEqual(json.loads((root/'result/report.json').read_text()), report)
            regions_file = root/'example/regions.json'
            original_regions = regions_file.read_text()
            regions = json.loads(original_regions)
            regions['reference_image'] = 7
            regions_file.write_text(json.dumps(regions))
            command[-1] = str(root/'invalid-regions')
            bad = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(bad.returncode, 2)
            self.assertNotIn('Traceback', bad.stderr)
            self.assertEqual(json.loads((root/'invalid-regions/report.json').read_text())['outcome'], 'error')
            regions_file.write_text(original_regions)
            (root/'aligned/alignment.json').write_text(json.dumps(dict(status='failure', reason='bad geometry')))
            (root/'aligned/aligned.png').unlink()
            command[-1] = str(root/'failure')
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 2, run.stdout+run.stderr)
            report = json.loads((root/'failure/report.json').read_text())
            self.assertEqual(report['outcome'], 'review')
            self.assertIn('bad geometry', report['reason'])
            self.assertIsNone(report['overlay'])
            self.assertFalse((root/'failure/overlay.png').exists())


if __name__ == '__main__':
    unittest.main()
