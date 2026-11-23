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

    def test_automatic_missing_checkpoint_tries_classical_registration_without_manual_points(self):
        payload = self.payload()
        payload['mode'] = 'automatic'
        with patch('pcb_landmarks.web.CHECKPOINT', Path(self.folder.name)/'absent.pt'):
            result = self.client.post('/api/inspections', json=payload).json()['photos'][0]
            detection = self.client.post(f"/api/landmarks/{payload['reference_id']}").json()
        self.assertEqual(result['outcome'], 'review')
        self.assertIn('on-board matches', result['alignment']['reason'])
        self.assertEqual(result['landmark_diagnostics']['inspection']['status'], 'failure')
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
        outline = [[0, 0], [319, 0], [319, 239], [0, 239]]
        response = self.client.post(f"/api/photos/{uploaded['id']}/component-proposals",
                                    json={'board_polygon': outline})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertGreater(len(result['components']), 0)
        self.assertFalse(result['verified'])
        self.assertEqual(result['board_polygon'], [[float(x), float(y)] for x, y in outline])
        self.assertTrue(all(part['candidate_status'] == 'UNKNOWN' for part in result['components']))

    def test_matching_reference_map_seeds_proposals_and_antigravity_import_is_validated(self):
        source = Path('PCB_Dataset_Pilot/images/val/ECCC5.jpg')
        response = self.client.post('/api/photos', files={
            'image': (source.name, source.read_bytes(), 'image/jpeg')})
        uploaded = response.json()
        proposals = self.client.post(f"/api/photos/{uploaded['id']}/component-proposals").json()['components']
        expected = json.loads(Path('configs/components-ECCC5.json').read_text(encoding='utf-8'))['components']
        from pcb_landmarks.component_detection import _box_iou
        self.assertEqual(sum(max(_box_iou(item['bbox_xyxy_px'], proposal['bbox_xyxy_px'])
                                 for proposal in proposals) >= .5 for item in expected), len(expected))

        golden = self.upload(self.reference, 'golden_reference.png')
        mapping = {'metadata': {'reference_image_id': 'golden_reference.png',
                                'image_dimensions': {'width': 320, 'height': 240, 'channels': 3}},
                   'components': [{'id': 'U1', 'description': 'Controller', 'bbox': [60, 45, 40, 40]}]}
        imported = self.client.post(
            f"/api/photos/{golden['id']}/component-map",
            files={'component_map': ('golden_components.json', json.dumps(mapping), 'application/json')})
        self.assertEqual(imported.status_code, 200, imported.text)
        imported_u1 = next(component for component in imported.json()['components'] if component['id'] == 'U1')
        self.assertEqual(imported_u1['bbox_xyxy_px'], [60, 45, 100, 85])
        mapping['metadata']['image_dimensions']['width'] = 321
        rejected = self.client.post(
            f"/api/photos/{golden['id']}/component-map",
            files={'component_map': ('golden_components.json', json.dumps(mapping), 'application/json')})
        self.assertEqual(rejected.status_code, 422)
        self.assertIn('dimensions', rejected.json()['detail'])

    def test_authenticated_platform_routes_enforce_roles(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.dict(os.environ, {'PCB_ADMIN_USERNAME': 'admin', 'PCB_ADMIN_PASSWORD': 'temporary-password'}, clear=False):
            client = TestClient(create_app(Path(folder.name)))
        login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'temporary-password'})
        self.assertEqual(login.status_code, 200, login.text)
        headers = {'Authorization': 'Bearer ' + login.json()['token']}
        self.assertEqual(client.get('/api/dashboard').status_code, 401)
        dashboard = client.get('/api/dashboard', headers=headers).json()
        self.assertEqual(dashboard['metrics']['total'], 0)
        self.assertEqual(dashboard['line']['status'], 'stopped')
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
        unknown = [dict(self.regions['components'][0], candidate_status='UNKNOWN')]
        unaccepted = client.post('/api/golden-config', headers=headers, json={
            'reference_id': reference['id'], 'components': unknown, 'mode': 'automatic'})
        self.assertEqual(unaccepted.status_code, 422)
        self.assertIn('accept', unaccepted.json()['detail'].lower())
        saved = client.post('/api/golden-config', headers=headers, json={
            'reference_id': reference['id'], 'components': self.regions['components'], 'mode': 'automatic'})
        self.assertEqual(saved.status_code, 200, saved.text)
        restored = client.get('/api/golden-config', headers=headers).json()
        self.assertEqual(restored['components'], self.regions['components'])
        self.assertTrue(restored['reference']['confirmed'])
        self.assertEqual(restored['reference']['image_url'], reference['image_url'])

    def test_live_import_accepts_multiple_images_and_rejects_invalid_input(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.dict(os.environ, {'PCB_ADMIN_USERNAME': 'admin', 'PCB_ADMIN_PASSWORD': 'temporary-password'}, clear=False):
            client = TestClient(create_app(Path(folder.name)))
        token = client.post('/api/auth/login', json={
            'username': 'admin', 'password': 'temporary-password'}).json()['token']
        headers = {'Authorization': 'Bearer ' + token}
        stream = io.BytesIO()
        Image.fromarray(self.reference).save(stream, format='PNG')
        content = stream.getvalue()
        files = [('images', (f'image-{index:02d}.png', content, 'image/png')) for index in range(15)]
        form = [('relative_paths', (None, f'nested/set-a/image-{index:02d}.png')) for index in range(15)]
        response = client.post('/api/simulation/import', headers=headers, files=[*files, *form])
        self.assertEqual(response.status_code, 200, response.text)
        imported = response.json()
        self.assertEqual(imported['accepted_count'], 15)
        self.assertTrue(Path(imported['dataset_directory']).is_dir())
        second = client.post('/api/simulation/import', headers=headers, files=[
            ('images', ('image-15.png', content, 'image/png')),
            ('images', ('bad.png', b'broken', 'image/png')),
            ('queue_id', (None, imported['queue_id'])),
            ('relative_paths', (None, 'nested/set-b/image-15.png')),
            ('relative_paths', (None, 'nested/set-b/bad.png')),
        ])
        self.assertEqual(second.status_code, 200, second.text)
        result = second.json()
        self.assertEqual((result['accepted_count'], result['skipped_count'], result['total_count']), (1, 1, 16))
        self.assertIn('ImageDecodeError', result['skipped'][0]['reason'])
        self.assertEqual(len(list(Path(result['dataset_directory']).rglob('*.png'))), 16)

    def test_real_inspection_alarms_persist_both_operator_decisions(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with patch.dict(os.environ, {'PCB_ADMIN_USERNAME': 'admin',
                                     'PCB_ADMIN_PASSWORD': 'temporary-password'}, clear=False):
            app = create_app(Path(folder.name))

        def upload(image, name):
            stream = io.BytesIO()
            Image.fromarray(image).save(stream, format='PNG')
            response = client.post('/api/photos', files={
                'image': (name, stream.getvalue(), 'image/png')})
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        with TestClient(app) as client:
            token = client.post('/api/auth/login', json={
                'username': 'admin', 'password': 'temporary-password'}).json()['token']
            headers = {'Authorization': 'Bearer ' + token}
            reference = upload(self.reference, 'reference.png')
            first = upload(self.inspection, 'alarm-one.png')
            second = upload(self.inspection, 'alarm-two.png')
            response = client.post('/api/inspections', json={
                'reference_id': reference['id'],
                'reference_points': self.rp.tolist(),
                'inspections': [
                    {'photo_id': first['id'], 'points': self.ip.tolist()},
                    {'photo_id': second['id'], 'points': self.ip.tolist()},
                ],
                'components': self.regions['components'],
                'mode': 'manual', 'sharpen': False, 'synthetic': True,
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual([photo['outcome'] for photo in response.json()['photos']],
                             ['defect', 'defect'])

            pending = client.get('/api/reviews', headers=headers).json()['reviews']
            self.assertEqual(len(pending), 2)
            dismissed = client.post(
                f"/api/reviews/{pending[0]['id']}/decision", headers=headers,
                json={'decision': 'false_alarm', 'note': 'Acceptance G'})
            confirmed = client.post(
                f"/api/reviews/{pending[1]['id']}/decision", headers=headers,
                json={'decision': 'confirmed_reject', 'note': 'Acceptance H'})
            self.assertEqual(dismissed.status_code, 200, dismissed.text)
            self.assertEqual(confirmed.status_code, 200, confirmed.text)
            metrics = client.get('/api/dashboard', headers=headers).json()['metrics']
            self.assertEqual((metrics['pending'], metrics['false_alarms'], metrics['rejected']),
                             (0, 1, 1))
            duplicate = client.post(
                f"/api/reviews/{pending[0]['id']}/decision", headers=headers,
                json={'decision': 'confirmed_reject'})
            self.assertEqual(duplicate.status_code, 409)


if __name__ == '__main__':
    unittest.main()
