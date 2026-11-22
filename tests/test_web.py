import io
import json
import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from comparison_fixture import comparison_pair
from pcb_landmarks.align import align_images
from pcb_landmarks.compare import compare_regions, load_config
from pcb_landmarks.web import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.client = TestClient(create_app(Path(self.folder.name)))
        self.reference, self.inspection, self.rp, self.ip, self.regions = comparison_pair()

    def upload(self, image, name='photo.png'):
        stream = io.BytesIO()
        Image.fromarray(image).save(stream, format='PNG')
        response = self.client.post('/api/photos', files={'image': (name, stream.getvalue(), 'image/png')})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def payload(self):
        ref, inspection = self.upload(self.reference), self.upload(self.inspection)
        return dict(reference_id=ref['id'], reference_points=self.rp.tolist(),
                    inspections=[dict(photo_id=inspection['id'], points=self.ip.tolist())],
                    components=self.regions['components'], mode='manual', sharpen=False, synthetic=True)

    def test_pipeline_matches_cli_functions_and_saves_assets(self):
        response = self.client.post('/api/inspections', json=self.payload())
        self.assertEqual(response.status_code, 200, response.text)
        batch = response.json()
        self.assertTrue(batch['synthetic'])
        actual = batch['photos'][0]
        aligned, _, mask = align_images(self.reference, self.inspection, self.rp, self.ip)
        expected = compare_regions(self.reference, aligned, mask, self.regions,
                                   load_config('configs/comparison.json'), dict(status='ok', reference_wh=[320, 240]))
        self.assertEqual(actual['components'], expected['components'])
        self.assertEqual(actual['outcome'], 'defect')
        for key in ['alignment_overlay_url', 'component_overlay_url', 'difference_overlay_url']:
            asset = self.client.get(actual[key])
            self.assertEqual(asset.status_code, 200)
            with Image.open(io.BytesIO(asset.content)) as image:
                self.assertEqual(image.size, (320, 240))
        self.assertEqual(self.client.get(batch['report_url']).json(), batch)

    def test_failed_photo_does_not_suppress_valid_sibling(self):
        payload = self.payload()
        bad = self.client.post('/api/photos', files={'image': ('broken.png', b'not an image', 'image/png')}).json()
        payload['inspections'] = [dict(photo_id=bad['id'], points=[]), *payload['inspections'],
                                  dict(payload['inspections'][0], points=[[1, 1]]*4)]
        response = self.client.post('/api/inspections', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        photos = response.json()['photos']
        self.assertEqual([p['outcome'] for p in photos], ['error', 'defect', 'review'])
        self.assertIsNone(photos[0]['component_overlay_url'])
        self.assertIsNone(photos[2]['alignment_overlay_url'])
        self.assertTrue(all(p['status'] == 'not_evaluated' for p in photos[2]['components']))

    def test_fifteen_inspections_keep_all_results_and_overlays(self):
        payload = self.payload()
        payload['inspections'] *= 15
        response = self.client.post('/api/inspections', json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        batch = response.json()
        self.assertEqual(len(batch['photos']), 15)
        for result in batch['photos']:
            for key in ['alignment_overlay_url', 'component_overlay_url']:
                self.assertEqual(self.client.get(result[key]).status_code, 200)
        self.assertEqual(self.client.get(batch['report_url']).json(), batch)
        self.assertEqual(self.client.get('/api/health').json()['max_photos'], 15)
        for index in [-1, 15]:
            self.assertEqual(self.client.get(f"/api/batches/{batch['batch_id']}/{index}/alignment").status_code, 404)

    def test_automatic_missing_checkpoint_is_explicit_and_never_manual_fallback(self):
        payload = self.payload()
        payload['mode'] = 'automatic'
        with patch('pcb_landmarks.web.CHECKPOINT', Path(self.folder.name)/'absent.pt'):
            result = self.client.post('/api/inspections', json=payload).json()['photos'][0]
            detection = self.client.post(f"/api/landmarks/{payload['reference_id']}").json()
        self.assertEqual(result['outcome'], 'review')
        self.assertIn('checkpoint_unavailable', result['alignment']['reason'])
        self.assertIn('checkpoint_unavailable', detection['reason'])
        self.assertTrue(all(p['score'] is None for p in result['components']))

    def test_batch_limits_ids_booleans_and_origin(self):
        payload = self.payload()
        for change in [dict(inspections=[]), dict(inspections=payload['inspections']*16),
                       dict(sharpen='false'), dict(mode='guess'), dict(components=[])]:
            self.assertEqual(self.client.post('/api/inspections', json=dict(payload, **change)).status_code, 422)
        payload['reference_id'] = '../configs/comparison.json'
        self.assertEqual(self.client.post('/api/inspections', json=payload).status_code, 404)
        self.assertEqual(self.client.post('/api/photos', headers={'Origin': 'https://external.example'},
                                         files={'image': ('x.png', b'x')}).status_code, 403)

    def test_upload_orientation_and_size_boundaries(self):
        image = Image.fromarray(self.reference)
        stream = io.BytesIO()
        exif = image.getexif()
        exif[274] = 6
        image.save(stream, format='JPEG', exif=exif)
        response = self.client.post('/api/photos', files={'image': ('rotated.jpg', stream.getvalue())})
        self.assertIn('EXIF', response.json()['error'])
        with patch('pcb_landmarks.web.MAX_UPLOAD', 10):
            self.assertEqual(self.client.post('/api/photos', files={'image': ('large.png', b'x'*11)}).status_code, 413)

    def test_annotation_limits_and_nonfinite_metadata_are_rejected(self):
        payload = self.payload()
        payload['components'][0]['name'] = 'x'*121
        self.assertEqual(self.client.post('/api/inspections', json=payload).status_code, 422)
        payload['components'][0]['name'] = 'chip'
        payload['components'][0]['bbox_xyxy_px'][0] = float('nan')
        response = self.client.post('/api/inspections', content=json.dumps(payload),
                                    headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 422)

    def test_corrupt_upload_after_yolo_import_stays_a_photo_error(self):
        from ultralytics import YOLO  # Loading the library replaces Pillow's global Image.open.
        self.assertIsNotNone(YOLO)
        response = self.client.post('/api/photos', files={'image': ('broken.png', b'not an image', 'image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertIn('ImageDecodeError', response.json()['error'])

    def test_health_needs_no_dataset_for_manual_demo(self):
        root = Path(self.folder.name)/'without dataset'
        (root/'configs').mkdir(parents=True)
        for name in ['landmarks.json', 'comparison.json']:
            (root/'configs'/name).write_bytes((Path('configs')/name).read_bytes())
        with patch('pcb_landmarks.web.ROOT', root):
            response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['landmark_names']), 4)

    def test_component_proposals_are_generated_for_uploaded_reference(self):
        uploaded = self.upload(self.reference)
        response = self.client.post(f"/api/photos/{uploaded['id']}/component-proposals")
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertGreater(len(result['components']), 0)
        self.assertFalse(result['verified'])
        self.assertTrue(all(part['candidate_status'] == 'UNKNOWN' for part in result['components']))

    def test_authenticated_platform_routes_enforce_roles(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.dict(os.environ, {'PCB_ADMIN_USERNAME': 'admin', 'PCB_ADMIN_PASSWORD': 'temporary-password'}, clear=False):
            client = TestClient(create_app(Path(folder.name)))
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'temporary-password'})
        self.assertEqual(login.status_code, 200, login.text)
        headers = {'Authorization': 'Bearer ' + login.json()['token']}
        self.assertEqual(client.get('/api/dashboard').status_code, 401)
        self.assertEqual(client.get('/api/dashboard', headers=headers).json()['metrics']['total'], 0)
        created = client.post('/api/users', headers=headers, json={
            'username': 'operator', 'display_name': 'Line Operator', 'role': 'operator',
            'password': 'operator-password'})
        self.assertEqual(created.status_code, 200, created.text)
        operator = client.post('/api/auth/login', json={
            'username': 'operator', 'password': 'operator-password'}).json()
        denied = client.get('/api/users', headers={'Authorization': 'Bearer ' + operator['token']})
        self.assertEqual(denied.status_code, 403)

    def test_approved_golden_configuration_persists_annotations(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.dict(os.environ, {'PCB_ADMIN_USERNAME': 'admin', 'PCB_ADMIN_PASSWORD': 'temporary-password'}, clear=False):
            client = TestClient(create_app(Path(folder.name)))
        token = client.post('/api/auth/login', json={
            'username': 'admin', 'password': 'temporary-password'}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        stream = io.BytesIO()
        Image.fromarray(self.reference).save(stream, format='PNG')
        reference = client.post('/api/photos', files={
            'image': ('golden.png', stream.getvalue(), 'image/png')}).json()
        premature = client.post('/api/golden-config', headers=headers, json={
            'reference_id': reference['id'], 'components': self.regions['components'], 'mode': 'automatic'})
        self.assertEqual(premature.status_code, 422)
        setup = client.post(f"/api/references/{reference['id']}", json={
            'points': self.rp.tolist(), 'board_polygon': [[0, 0], [319, 0], [319, 239], [0, 239]]})
        self.assertEqual(setup.status_code, 200, setup.text)
        saved = client.post('/api/golden-config', headers=headers, json={
            'reference_id': reference['id'], 'components': self.regions['components'], 'mode': 'automatic'})
        self.assertEqual(saved.status_code, 200, saved.text)
        restored = client.get('/api/golden-config', headers=headers).json()
        self.assertEqual(restored['components'], self.regions['components'])
        self.assertTrue(restored['reference']['confirmed'])
        self.assertEqual(restored['reference']['image_url'], reference['image_url'])


if __name__ == '__main__':
    unittest.main()
