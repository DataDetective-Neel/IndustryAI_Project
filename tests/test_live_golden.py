import io
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

from pcb_landmarks.web import create_app


class LiveGoldenTests(unittest.TestCase):
    def test_real_model_reference_self_rotation_replacement_and_failed_upload(self):
        source = Path(os.environ.get('PCB_REPAIR_DATASET', 'A:/IndustryAI_Dataset_Worktree/dataset_generation'))/'golden/golden_reference.png'
        if not source.is_file():
            self.skipTest('ELEGOO source image is not installed')
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'PCB_ADMIN_USERNAME':'live-test', 'PCB_ADMIN_PASSWORD':'local-live-test-password'}):
            client = TestClient(create_app(Path(directory)/'storage'))
            login = client.post('/api/auth/login', json=dict(username='live-test',password='local-live-test-password'))
            headers = {'Authorization':f"Bearer {login.json()['token']}"}
            empty = client.get('/api/simulation/reference',headers=headers)
            self.assertEqual(empty.status_code,200)
            self.assertIsNone(empty.json())
            def golden(data, name):
                return client.post('/api/simulation/reference',headers=headers,
                                   files={'image':(name,data,'image/png' if name.endswith('.png') else 'image/jpeg')})
            first = golden(source.read_bytes(),'golden.png')
            self.assertEqual(first.status_code,200,first.text)
            config = first.json()
            self.assertGreater(len(config['components']), 20)
            self.assertEqual(len(config['reference']['points']),4)
            image = np.asarray(Image.open(source).convert('RGB'))
            rotated = cv2.warpAffine(image,cv2.getRotationMatrix2D((image.shape[1]/2,image.shape[0]/2),3,1), (image.shape[1],image.shape[0]))
            records=[]
            for data in [image,rotated]:
                stream=io.BytesIO();Image.fromarray(data).save(stream,format='PNG')
                records.append(client.post('/api/photos',files={'image':('input.png',stream.getvalue(),'image/png')}).json())
            result=client.post('/api/inspections',json=dict(reference_id=config['reference_id'],mode='automatic',
                components=config['components'],inspections=[dict(photo_id=p['id']) for p in records])).json()
            for row in result['photos']:
                self.assertEqual(row['alignment']['status'],'ok',row['alignment'])
                self.assertTrue(row['components_evaluated'])
            self.assertFalse(any(p['status']=='missing' for p in result['photos'][0]['components']))
            bad=golden(b'bad png','invalid.png')
            self.assertEqual(bad.status_code,422)
            self.assertEqual(client.get('/api/simulation/reference',headers=headers).json()['reference_id'],config['reference_id'])
            queue=Path(directory)/'frames';queue.mkdir()
            for name in ['1.png','2.png']: Image.fromarray(image).save(queue/name)
            start=client.post('/api/simulation/start',headers=headers,json=dict(dataset_directory=str(queue),interval=1))
            self.assertEqual(start.status_code,200,start.text)
            def wait(predicate):
                deadline=time.monotonic()+45
                while time.monotonic()<deadline:
                    state=client.get('/api/simulation',headers=headers).json()
                    if predicate(state): return state
                    time.sleep(.05)
                self.fail('Live frame processing timed out')
            state=wait(lambda s:s['processed']==1)
            self.assertEqual(state['last_result']['golden_reference_id'],config['reference_id'])
            self.assertEqual(client.post('/api/simulation/pause',headers=headers).status_code,200)
            stream=io.BytesIO();Image.fromarray(image).save(stream,format='JPEG',quality=98)
            second=golden(stream.getvalue(),'replacement.jpeg')
            self.assertEqual(second.status_code,200,second.text)
            self.assertNotEqual(second.json()['reference_id'],config['reference_id'])
            self.assertEqual(client.post('/api/simulation/resume',headers=headers).status_code,200)
            state=wait(lambda s:s['status']=='completed')
            self.assertEqual(state['processed'],2)
            self.assertEqual(state['last_result']['golden_reference_id'],second.json()['reference_id'])
            self.assertEqual(state['last_result']['alignment']['status'],'ok')
