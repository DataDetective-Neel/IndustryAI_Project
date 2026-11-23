"""Exercise real HTTP inspection paths; annotations are never prediction inputs."""
import argparse
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

from .component_detection import import_component_map
from .data import read_image
from .web import create_app


def run(dataset, output):
    output.mkdir(parents=True, exist_ok=True)
    golden = read_image(dataset/'golden/golden_reference.png')
    components = import_component_map(json.loads((dataset/'golden/golden_components.json').read_text()),
                                      golden.size, 'golden_reference.png')
    rgb = np.asarray(golden)
    cases = dict(self=rgb,
                 translation=cv2.warpAffine(rgb, np.float32([[1, 0, 9], [0, 1, -7]]), golden.size),
                 rotation=cv2.warpAffine(rgb, cv2.getRotationMatrix2D((golden.width/2, golden.height/2), 4, 1), golden.size),
                 misaligned_002=np.asarray(read_image(dataset/'images/misaligned/misaligned_002.png')),
                 missing_001=np.asarray(read_image(dataset/'images/missing/missing_001.png')),
                 poor_quality=np.full_like(rgb, 125))
    report = dict(dataset=str(dataset), prediction_inputs='Golden component map and decoded photos only; no defect annotations', cases={})
    with tempfile.TemporaryDirectory() as temporary:
        client = TestClient(create_app(Path(temporary)))

        def upload(image, filename='board.png'):
            stream = io.BytesIO()
            Image.fromarray(image).save(stream, format='PNG')
            response = client.post('/api/photos', files={'image': (filename, stream.getvalue(), 'image/png')})
            response.raise_for_status()
            return response.json()['id']

        reference = upload(rgb, 'golden_reference.png')
        setup = client.post(f'/api/references/{reference}/automatic')
        setup.raise_for_status()
        report['reference'] = setup.json()

        def inspect(name, reference, image, parts):
            response = client.post('/api/inspections', json=dict(reference_id=reference, mode='automatic',
                components=parts, inspections=[dict(photo_id=upload(image))]))
            response.raise_for_status()
            batch = response.json()
            result = batch['photos'][0]
            for key in ['alignment_overlay_url', 'component_overlay_url', 'difference_overlay_url']:
                if result.get(key):
                    asset = client.get(result[key])
                    asset.raise_for_status()
                    filename = f'{name}-{key}.png'
                    (output/filename).write_bytes(asset.content)
                    result[key] = filename
            report['cases'][name] = result
            print(name, result['alignment']['status'], result['outcome'],
                  {s: sum(p['status'] == s for p in result['components']) for s in ['present', 'misaligned', 'missing', 'uncertain', 'not_evaluated']}, flush=True)
            return result

        for name, image in cases.items():
            inspect(name, reference, image, components)
        # Different catalog layouts supply positive mismatch evidence.
        a = np.asarray(read_image('PCB_Dataset_Pilot/images/train/ACCC5.jpg'))
        e = np.asarray(read_image('PCB_Dataset_Pilot/images/val/ECCC5.jpg'))
        inspect('different_design', upload(a), e, [dict(id='probe', name='probe', bbox_xyxy_px=[300, 300, 350, 350])])
        manual = upload(rgb)
        with patch('pcb_landmarks.web.automatic_reference', side_effect=ValueError('Automatic outline unavailable')):
            failure = client.post(f'/api/references/{manual}/automatic')
        report['manual_fallback_status'] = failure.status_code
        response = client.post(f'/api/references/{manual}', json={k: setup.json()[k] for k in ['points', 'board_polygon']})
        response.raise_for_status()
        inspect('manual_saved_reuse_1', manual, cases['translation'], components)
        inspect('manual_saved_reuse_2', manual, cases['rotation'], components)
        (output/'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('runs/repair-acceptance'))
    args = parser.parse_args()
    run(args.dataset, args.output)


if __name__ == '__main__':
    main()
