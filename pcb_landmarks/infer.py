"""Load PCB-specific local weights and return ordered landmarks or explicit failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import cv2

from .data import DEFAULT_DATA, load_data, read_image
from .compatibility import calibrated_mounts

# Set before importing Ultralytics: even its startup connectivity probe stays offline.
os.environ['YOLO_OFFLINE'] = 'true'


def refine_mounts(image, points):
    """Fit visible gold mounting rims near model proposals for the pilot boards."""
    image = np.asarray(image)
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (5, 50, 25), (45, 255, 255))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_NONE)
    candidates = []
    for i, contour in enumerate(contours):
        if len(contour) < 12:
            continue
        (x, y), (a, b), _ = cv2.fitEllipse(contour)
        if not (max(18, .045*min(width, height)) <= min(a, b) <= max(a, b) <= .1*min(width, height)):
            continue
        if min(a, b)/max(a, b) < .6 or cv2.contourArea(contour)/(np.pi*a*b/4) < .8:
            continue
        if not (0 <= round(x) < width and 0 <= round(y) < height) or hsv[round(y), round(x), 2] > 225:
            continue
        candidates.append((x, y, max(a, b)))
    # Inner/outer edges of one annulus must count as one hole.
    rings = []
    for x, y, diameter in sorted(candidates, key=lambda p: -p[2]):
        if all(np.hypot(x-r[0], y-r[1]) > .2*diameter for r in rings):
            rings.append((x, y, diameter))
    refined, rows, used = [], [], set()
    limit = .15*np.hypot(width, height)
    for identity, point in enumerate(np.asarray(points)):
        distances = np.linalg.norm(np.array(rings)[:, :2]-point, axis=1) if rings else np.array([])
        nearby = np.flatnonzero(distances <= limit)
        if len(nearby) != 1 or int(nearby[0]) in used:
            return None, dict(status='failure', reason='missing_or_ambiguous_nearby_mounting_ring',
                              landmark_id=identity, max_shift_px=float(limit), points=rows)
        index = int(nearby[0])
        used.add(index)
        refined.append(rings[index][:2])
        rows.append(dict(id=identity, raw_xy=np.asarray(point).tolist(), refined_xy=list(rings[index][:2]),
                         shift_px=float(distances[index])))
    return np.array(refined), dict(status='ok', method='local gold mounting rim ellipse center',
                                   max_shift_px=float(limit), points=rows)


def verify_mount_orientation(reference, image, points):
    """Use the known board's interior pattern to verify cyclic landmark identities."""
    def features(array):
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY).astype(np.float32)
        return cv2.magnitude(cv2.Sobel(gray, cv2.CV_32F, 1, 0),
                             cv2.Sobel(gray, cv2.CV_32F, 0, 1))[2:-2, 2:-2].ravel()
    target = np.float32([[0, 0], [255, 0], [255, 255], [0, 255]])
    template, scores = features(reference), []
    for shift in range(4):
        matrix = cv2.getPerspectiveTransform(np.roll(np.float32(points), -shift, axis=0), target)
        patch = cv2.warpPerspective(np.asarray(image), matrix, (256, 256))
        current = features(patch)
        scores.append(float(np.corrcoef(template, current)[0, 1]) if min(template.std(), current.std()) >= 1 else -1.)
    order = np.argsort(scores)
    best = int(order[-1])
    margin = scores[best]-scores[int(order[-2])]
    valid = scores[best] >= .35 and margin >= .15
    return (best if valid else None), dict(status='ok' if valid else 'failure', scores=scores,
                                          cyclic_shift=best, score=scores[best], margin=margin)


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


def assess_mounts(image, boxes, scores, keypoints, names, board_conf, point_conf):
    verified = []
    rejections = []
    candidates = [i for i, score in enumerate(scores) if np.isfinite(score) and score > board_conf]
    for i in candidates:
        points = keypoints[i] if i < len(keypoints) else []
        candidate = assess([boxes[i]], [scores[i]], [points], names, image.size, board_conf, point_conf)
        if candidate['status'] != 'ok':
            continue
        refined, details = refine_mounts(image, keypoints[i, :, :2])
        if refined is None:
            rejections.append(dict(board_id=i, **details))
        if refined is not None:
            candidate = assess([boxes[i]], [scores[i]], [np.column_stack((refined, keypoints[i, :, 2]))],
                               names, image.size, board_conf, point_conf)
            candidate.update(refinement=details, selected_board_id=i)
            if candidate['status'] == 'ok':
                verified.append(candidate)
    if not verified:
        result = assess(boxes, scores, keypoints, names, image.size, board_conf, point_conf)
        if result['status'] == 'ok' or result['reason'] == 'ambiguous_boards':
            result.update(status='failure', reason='mounting_holes_not_verified', landmarks=[])
        result['mounting_verification'] = dict(status='failure', candidates=rejections)
        return result
    selected = max(verified, key=lambda c: c['board_confidence'])
    box = np.asarray(selected['bbox_xyxy'])
    for i in candidates:
        other = np.asarray(boxes[i])
        if not np.isfinite(other).all():
            return dict(status='failure', reason='nonfinite_prediction', landmarks=[])
        intersection = np.maximum(0, np.minimum(box[2:], other[2:])-np.maximum(box[:2], other[:2])).prod()
        union = (box[2:]-box[:2]).prod() + (other[2:]-other[:2]).prod() - intersection
        if union <= 0 or intersection/union < .8:
            return dict(status='failure', reason='ambiguous_boards', landmarks=[])
    target = np.array([[p['x'], p['y']] for p in selected['landmarks']])
    for candidate in verified:
        points = np.array([[p['x'], p['y']] for p in candidate['landmarks']])
        if np.linalg.norm(points-target, axis=1).max() > 1:
            return dict(status='failure', reason='ambiguous_verified_holes', landmarks=[])
    return selected


class LandmarkDetector:
    def __init__(self, checkpoint, data=DEFAULT_DATA, device='cpu', imgsz=640, expected_sha256=None,
                 refine_mounting_holes=False, mounting_reference=None, calibrated_mounting_holes=False):
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
        self.refine_mounting_holes = refine_mounting_holes
        self.calibrated_mounting_holes = calibrated_mounting_holes
        self.mounting_reference = np.asarray(read_image(mounting_reference)) if mounting_reference else None
        if self.mounting_reference is not None and self.mounting_reference.shape != (256, 256, 3):
            raise ValueError('Mounting reference must be the calibrated 256x256 RGB board pattern')

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
        if getattr(self, 'refine_mounting_holes', False):
            result = assess_mounts(image, boxes, scores, keypoints, self.names, board_conf, point_conf)
        if getattr(self, 'mounting_reference', None) is not None and result['status'] == 'ok':
            shift, details = verify_mount_orientation(self.mounting_reference, image,
                                                      [[p['x'], p['y']] for p in result['landmarks']])
            result['orientation_verification'] = details
            if shift is None:
                result.update(status='failure', reason='mounting_pattern_not_verified', landmarks=[])
            else:
                ordered = result['landmarks'][shift:] + result['landmarks'][:shift]
                result['landmarks'] = [dict(p, name=name, raw_landmark_id=(i+shift) % 4)
                                       for i, (name, p) in enumerate(zip(self.names, ordered))]
        model_verdict = dict(status=result['status'], reason=result['reason'],
                             refinement=result.get('refinement'),
                             orientation_verification=result.get('orientation_verification'))
        if getattr(self, 'calibrated_mounting_holes', False):
            points, evidence = calibrated_mounts(image)
            if points is not None:
                result.pop('orientation_verification', None)
                result.pop('board_confidence', None)
                result.update(status='ok', reason=None, source='calibrated_layout_mounts',
                              refinement=dict(status='ok', method=evidence['method'], points=evidence['points']),
                              landmarks=[dict(name=name, x=float(p[0]), y=float(p[1]), confidence=None)
                                         for name, p in zip(self.names, points)])
            elif evidence['reason'] != 'layout_not_calibrated_for_automatic_mounts' or evidence['layout']['status'] == 'REVIEW':
                result.update(status='failure', reason=evidence['reason'], landmarks=[])
            result['calibrated_mounting'] = evidence
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
                                   accepted=result.get('source') != 'calibrated_layout_mounts'
                                            and result['status'] == 'ok' and verdict['status'] == 'ok'
                                            and i == result.get('selected_board_id', i),
                                   rejection_reason=(('replaced_by_verified_calibrated_mounts' if result.get('source') == 'calibrated_layout_mounts' else None)
                                                     or result['reason'] or verdict['reason'] or
                                                     ('duplicate_board_proposal' if i != result.get('selected_board_id', i) else None))))
        result['diagnostics'] = dict(checkpoint_path=self.checkpoint, format='one pcb detection; four keypoints',
                                   landmark_order=self.names, board_conf=board_conf, point_conf=point_conf,
                                   raw_minimum_confidence=0.001, imgsz=self.imgsz,
                                   coordinates='decoded original RGB pixels; Ultralytics reverses letterbox',
                                   refinement=result.get('refinement'),
                                   orientation_verification=model_verdict.get('orientation_verification'),
                                   model_postprocessing=model_verdict,
                                   calibrated_mounting=result.get('calibrated_mounting'),
                                   candidates=candidates)
        result['image_wh'] = list(image.size)
        result['checkpoint_sha256'] = self.sha256
        result['model_inference_ran'] = True
        result['raw_board_predictions'] = len(boxes)
        result['verification_status'] = 'verified' if result['status'] == 'ok' else 'rejected'
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
                                    expected_sha256=config['checkpoint_sha256'],
                                    refine_mounting_holes=config.get('refine_mounting_holes', False),
                                    mounting_reference=(Path(args.config).resolve().parent/config['mounting_reference']
                                                        if config.get('mounting_reference') else None),
                                    calibrated_mounting_holes=config.get('calibrated_mounting_holes', False))
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
