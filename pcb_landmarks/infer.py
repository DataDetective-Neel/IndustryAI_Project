"""Load PCB-specific local weights and return ordered landmarks or explicit failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from .data import DEFAULT_DATA, load_data, read_image

# Set before importing Ultralytics: even its startup connectivity probe stays offline.
os.environ['YOLO_OFFLINE'] = 'true'


def assess(boxes, scores, keypoints, names, size, board_conf, point_conf):
    failure = lambda reason: dict(status='failure', reason=reason, landmarks=[])
    candidates = [i for i, score in enumerate(scores) if np.isfinite(score) and score > board_conf]
    if not candidates:
        return failure('no_confident_board')
    if len(candidates) != 1:
        return failure('ambiguous_boards')
    index = candidates[0]
    if index >= len(keypoints):
        return failure('incomplete_landmarks')
    points = np.asarray(keypoints[index])
    if points.shape != (4, 3):
        return failure('incomplete_landmarks')
    if not np.isfinite(points).all() or not np.isfinite(boxes[index]).all():
        return failure('nonfinite_prediction')
    if (points[:, 2] < point_conf).any() or (points[:, 2] > 1).any():
        return failure('low_landmark_confidence')
    width, height = size
    if (points[:, :2] < 0).any() or (points[:, 0] >= width).any() or (points[:, 1] >= height).any():
        return failure('landmarks_outside_image')
    if (points[:, :2] == 0).any():
        return failure('edge_clipped_landmarks')
    if len(np.unique(points[:, :2], axis=0)) != 4:
        return failure('coincident_landmarks')
    edges = np.roll(points[:, :2], -1, axis=0) - points[:, :2]
    next_edges = np.roll(edges, -1, axis=0)
    turns = edges[:, 0] * next_edges[:, 1] - edges[:, 1] * next_edges[:, 0]
    if (turns <= 0).any():
        return failure('invalid_landmark_order_or_geometry')
    return dict(status='ok', reason=None, board_confidence=float(scores[index]),
                bbox_xyxy=[float(v) for v in boxes[index]],
                landmarks=[dict(name=name, x=float(p[0]), y=float(p[1]), confidence=float(p[2]))
                           for name, p in zip(names, points)])


class LandmarkDetector:
    def __init__(self, checkpoint, data=DEFAULT_DATA, device='cpu', imgsz=640, expected_sha256=None):
        path = Path(checkpoint).resolve(strict=True)
        if not path.is_file() or path.suffix.lower() != '.pt':
            raise ValueError('Checkpoint must be an existing local .pt file')
        self.checkpoint = str(path)
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        if expected_sha256 is not None and self.sha256 != expected_sha256:
            raise ValueError('Checkpoint hash does not match frozen configuration')
        _, _, self.names = load_data(data)
        from ultralytics import YOLO
        from ultralytics.utils import SETTINGS
        SETTINGS.update({'sync': False})
        self.model = YOLO(str(path), task='pose')
        if (self.model.task != 'pose' or self.model.names != {0: 'pcb'}
                or self.model.model.yaml.get('kpt_shape') != [4, 3]
                or getattr(self.model.model, 'kpt_names', {}).get(0) != self.names):
            raise ValueError('Checkpoint is not the trained PCB four-landmark schema')
        self.device, self.imgsz = device, imgsz

    def raw(self, image, minimum_confidence=0.001):
        result = self.model.predict(source=image, imgsz=self.imgsz, device=self.device,
                                    conf=minimum_confidence, max_det=20, verbose=False,
                                    save=False, augment=False)[0]
        boxes = result.boxes.xyxy.cpu().numpy()
        scores = result.boxes.conf.cpu().numpy()
        points = result.keypoints.data.cpu().numpy() if result.keypoints is not None else []
        return boxes, scores, points

    def predict(self, image, board_conf, point_conf):
        if not (0 < board_conf <= 1 and 0 < point_conf <= 1):
            raise ValueError('Confidence thresholds must be in (0, 1]')
        image = read_image(image) if isinstance(image, (str, Path)) else image
        boxes, scores, keypoints = self.raw(image, 0.001)
        result = assess(boxes, scores, keypoints, self.names, image.size, board_conf, point_conf)
        candidates = []
        for i, (box, score) in enumerate(zip(boxes, scores)):
            points = keypoints[i] if i < len(keypoints) else []
            verdict = assess([box], [score], [points], self.names, image.size, board_conf, point_conf)
            rows = []
            for identity, (name, point) in enumerate(zip(self.names, points)):
                x, y, confidence = map(float, point)
                reasons = []
                if not np.isfinite(point).all():
                    reasons.append('nonfinite_prediction')
                if not point_conf <= confidence <= 1:
                    reasons.append('low_landmark_confidence')
                if not (0 < x < image.width and 0 < y < image.height):
                    reasons.append('outside_or_clipped_image')
                rows.append(dict(id=identity, name=name, x=x if np.isfinite(x) else None,
                                 y=y if np.isfinite(y) else None,
                                 confidence=confidence if np.isfinite(confidence) else None,
                                 point_rejection_reasons=reasons))
            candidates.append(dict(board_id=i, class_id=0, board_confidence=float(score),
                                   bbox_xyxy=np.asarray(box).tolist(), landmarks=rows,
                                   accepted=result['status'] == 'ok' and verdict['status'] == 'ok',
                                   rejection_reason=result['reason'] or verdict['reason']))
        result['diagnostics'] = dict(checkpoint_path=self.checkpoint, format='one pcb detection; four keypoints',
                                   landmark_order=self.names, board_conf=board_conf, point_conf=point_conf,
                                   raw_minimum_confidence=0.001, imgsz=self.imgsz,
                                   coordinates='decoded original RGB pixels; Ultralytics reverses letterbox',
                                   candidates=candidates)
        result['image_wh'] = list(image.size)
        result['checkpoint_sha256'] = self.sha256
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', required=True)
    parser.add_argument('--source', required=True)
    parser.add_argument('--config', required=True, help='Validation-selected JSON configuration')
    parser.add_argument('--data', default=DEFAULT_DATA)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--output')
    args = parser.parse_args()
    try:
        config = json.loads(Path(args.config).read_text(encoding='utf-8'))
        detector = LandmarkDetector(args.checkpoint, args.data, args.device, config['imgsz'],
                                    expected_sha256=config['checkpoint_sha256'])
        if config['checkpoint_sha256'] != detector.sha256 or config['landmark_order'] != detector.names:
            raise ValueError('Configuration does not match checkpoint hash/landmark order')
        result = detector.predict(args.source, config['board_conf'], config['point_conf'])
    except Exception as error:
        result = dict(status='failure', reason=f'{type(error).__name__}: {error}', landmarks=[])
    payload = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        Path(args.output).write_text(payload + '\n', encoding='utf-8')
    print(payload)
    raise SystemExit(0 if result['status'] == 'ok' else 2)


if __name__ == '__main__':
    main()
