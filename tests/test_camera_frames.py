"""Camera transport uses the same backend pipeline as saved image inspection."""
import io
import os
import unittest
from unittest.mock import patch

from PIL import Image

import test_reference_reuse as fixtures


class CameraFrameTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, {'PCB_ADMIN_USERNAME': 'camera', 'PCB_ADMIN_PASSWORD': 'camera-local-password'}):
            fixtures.ReferenceReuseTests.setUp(self)

    upload = fixtures.ReferenceReuseTests.upload
    setup_reference = fixtures.ReferenceReuseTests.setup_reference

    def test_camera_frame_uses_selected_reference_and_rejects_stale_frames(self):
        self.setup_reference()
        # Establish a local user through the existing setup workflow.
        with patch.dict(os.environ, {'PCB_ADMIN_USERNAME': 'camera', 'PCB_ADMIN_PASSWORD': 'camera-local-password'}):
            login = self.client.post('/api/auth/login', json=dict(username='camera', password='camera-local-password'))
        self.assertEqual(login.status_code, 200, login.text)
        headers = {'Authorization': f"Bearer {login.json()['token']}"}
        saved = self.client.post('/api/golden-config', headers=headers, json=dict(reference_id=self.ref,
            components=[dict(id='part', name='part', bbox_xyxy_px=[180, 180, 220, 220])]))
        self.assertEqual(saved.status_code, 200, saved.text)
        stream = io.BytesIO(); Image.fromarray(self.reference).save(stream, format='PNG')
        def frame(reference_id, content=stream.getvalue()):
            return self.client.post('/api/live/frame', headers=headers, data={'reference_id': reference_id},
                files={'image': ('camera.png', content, 'image/png')})
        self.assertEqual(frame('0'*32).status_code, 409)
        self.assertEqual(frame(self.ref, b'corrupt').status_code, 422)
        with patch('pcb_landmarks.web._detector', side_effect=ValueError('No YOLO in synthetic fixture')):
            response = frame(self.ref)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['golden_reference_id'], self.ref)
        self.assertFalse(result['simulated'])
        self.assertTrue(result['components_evaluated'])
        self.assertEqual(result['alignment']['verification_status'], 'verified')
        # A later Lab save must replace a prior live-upload selection, including corrections.
        components = [dict(id='corrected', name='Corrected box', bbox_xyxy_px=[180, 180, 225, 225])]
        with patch('pcb_landmarks.web.propose_components', return_value=dict(components=components)):
            uploaded = self.client.post('/api/simulation/reference', headers=headers,
                files={'image': ('reference.png', stream.getvalue(), 'image/png')})
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        self.assertNotEqual(uploaded.json()['reference_id'], self.ref)
        saved = self.client.post('/api/golden-config', headers=headers,
            json=dict(reference_id=self.ref, components=components))
        self.assertEqual(saved.status_code, 200, saved.text)
        selected = self.client.get('/api/simulation/reference', headers=headers).json()
        self.assertEqual(selected['reference_id'], self.ref)
        self.assertEqual(selected['components'], components)
