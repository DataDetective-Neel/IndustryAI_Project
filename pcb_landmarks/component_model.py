"""Pretrained ParsaVictor component locator; no training or contour proposals."""
import hashlib
import json
import os
import threading
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from .parsa_tiling import tile_inference

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.Lock()
os.environ['YOLO_OFFLINE'] = 'true'


@lru_cache(maxsize=1)
def component_model():
    from ultralytics import YOLO
    config = json.loads((ROOT/'configs/component_model.json').read_text())
    path = Path(os.environ.get('PCB_COMPONENT_CHECKPOINT', ROOT/config['checkpoint_path']))
    if not path.is_file():
        raise ValueError(f'Component checkpoint unavailable: {path}. Install ParsaVictor any_best.pt.')
    if hashlib.sha256(path.read_bytes()).hexdigest() != config['checkpoint_sha256']:
        raise ValueError('Component checkpoint SHA256 does not match the configured pretrained weights')
    return YOLO(str(path)), config


def detect_components(rgb, polygon, maximum=1000):
    with LOCK:
        model, config = component_model()
        boxes = tile_inference(model, cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
            tile_size=config['tile_size'], overlap=config['overlap'],
            conf=config['confidence'], iou=config['iou'])
    height, width = rgb.shape[:2]
    found = []
    for x1, y1, x2, y2, score, cls in sorted(boxes, key=lambda b: -b[4]):
        box = [max(0, int(np.floor(x1))), max(0, int(np.floor(y1))),
               min(width, int(np.ceil(x2))), min(height, int(np.ceil(y2)))]
        if (box[2]-box[0] < 5 or box[3]-box[1] < 5 or
                cv2.pointPolygonTest(np.float32(polygon), ((box[0]+box[2])/2, (box[1]+box[3])/2), False) < 0):
            continue
        found.append((box, float(score), int(cls)))
    if len(found) > maximum:
        raise ValueError(f'{len(found)} components detected; exceeds supported limit {maximum}. Use a smaller board crop.')
    if not found:
        raise ValueError('No confident components detected; correct components manually or retake the golden image.')
    found.sort(key=lambda p: (p[0][1], p[0][0]))
    return [dict(id=f'AUTO-{i:03d}', name=f'Component {i:03d}', bbox_xyxy_px=box,
                 center_xy_px=[(box[0]+box[2])/2, (box[1]+box[3])/2],
                 width_px=box[2]-box[0], height_px=box[3]-box[1],
                 candidate_status='UNKNOWN', proposal_confidence=score,
                 proposal_evidence=dict(source='parsa_yolo26', class_id=cls,
                    class_name=model.names[cls], checkpoint_sha256=config['checkpoint_sha256']))
            for i, (box, score, cls) in enumerate(found, 1)]
